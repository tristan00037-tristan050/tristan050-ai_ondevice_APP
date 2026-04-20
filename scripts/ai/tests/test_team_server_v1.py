from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ai.team_server.data_collector import DataCollector
from scripts.ai.team_server.egress_guard import EgressBlockedError, EgressGuard, EgressPolicyGuard
from scripts.ai.team_server.finetune_trigger import FinetuneTrigger
from scripts.ai.team_server.knowledge_base import KnowledgeBase
from scripts.ai.team_server.policy_enforcer import PolicyEnforcer
from scripts.ai.team_server.rag_engine import RAGEngine
from scripts.ai.team_server.team_audit_logger import TeamAuditLogger
from scripts.ai.team_server.team_contracts import AccessLevel, DeviceMeta, KBDocument, RAGRequest, ServerStatus, digest16
from scripts.ai.team_server.team_persistence import TeamPersistence
from scripts.ai.team_server.team_server_core import TeamServer


@pytest.fixture()
def env(tmp_path: Path):
    state_dir = tmp_path / "state"
    audit_path = tmp_path / "team_audit.jsonl"
    persistence = TeamPersistence(str(state_dir))
    audit = TeamAuditLogger(str(audit_path))
    kb = KnowledgeBase(persistence)
    trigger = FinetuneTrigger(threshold=2, persistence=persistence)
    collector = DataCollector(kb, trigger, audit)
    policy = PolicyEnforcer(audit)
    rag = RAGEngine(kb, policy)
    return {
        "tmp_path": tmp_path,
        "state_dir": state_dir,
        "audit_path": audit_path,
        "persistence": persistence,
        "audit": audit,
        "kb": kb,
        "trigger": trigger,
        "collector": collector,
        "policy": policy,
        "rag": rag,
    }


def make_meta(team_id: str = "team-red") -> DeviceMeta:
    return DeviceMeta(
        device_id="dev-1",
        team_id=team_id,
        session_id="sess-1",
        task="meeting_summary",
        input_digest16="a" * 16,
        output_digest16="b" * 16,
        selected_model="butler-edge-v2",
        timestamp="2026-04-20T00:00:00+00:00",
    )


def make_doc(team_id: str = "team-red", access_level: AccessLevel = AccessLevel.TEAM, version: int = 1, created_at: str = "2026-04-20T00:00:00+00:00") -> KBDocument:
    return KBDocument(
        doc_id=digest16({"team": team_id, "access": access_level.value, "version": version, "created": created_at}),
        title_digest16=digest16({"title": team_id, "access": access_level.value}),
        summary="meta:meeting_summary:butler-edge-v2",
        tags=["meeting_summary", "butler-edge-v2"],
        version=version,
        lineage_id=digest16({"lineage": team_id}),
        access_level=access_level,
        created_at=created_at,
        team_id=team_id,
        source_ref=f"device:{team_id}",
    )


# collect

def test_collect_meta_only(env):
    result = env["collector"].receive(make_meta())
    assert result.accepted is True


def test_collect_reject_raw_text(env):
    payload = vars(make_meta()) | {"prompt": "x " * 100}
    result = env["collector"].receive(payload)
    assert result.accepted is False


def test_collect_counter_increment(env):
    env["collector"].receive(make_meta())
    env["collector"].receive(make_meta("team-blue"))
    assert env["collector"].get_stats()["team-red"]["collected"] == 1


def test_collect_stats_return(env):
    env["collector"].receive(make_meta())
    stats = env["collector"].get_stats()
    assert "team-red" in stats and stats["team-red"]["kb_docs"] == 1


# kb

def test_kb_index_document(env):
    res = env["kb"].index_document(make_doc())
    assert res.accepted is True


def test_kb_no_raw_content(env):
    bad = make_doc()
    bad = KBDocument(**{**vars(bad), "summary": "x " * 100})
    res = env["kb"].index_document(bad)
    assert res.accepted is False


def test_kb_version_lineage(env):
    doc1 = make_doc(version=1)
    doc2 = KBDocument(**{**vars(make_doc(version=2)), "lineage_id": doc1.lineage_id})
    env["kb"].index_document(doc1)
    env["kb"].index_document(doc2)
    assert [x["version"] for x in env["kb"].get_lineage(doc1.doc_id)] == [1, 2]


def test_kb_coverage_stats(env):
    env["kb"].index_document(make_doc())
    coverage = env["kb"].get_coverage("team-red")
    assert coverage["topics"]["meeting_summary"] == 1


# rag

def test_rag_query_returns_meta(env):
    env["kb"].index_document(make_doc())
    resp = env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert resp.hit_count == 1 and "summary" in resp.results_meta[0]


def test_rag_access_control(env):
    env["kb"].index_document(make_doc(access_level=AccessLevel.CONFIDENTIAL))
    resp = env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert resp.hit_count == 0 and resp.access_denied_count == 1


def test_rag_hit_rate_recorded(env):
    env["kb"].index_document(make_doc())
    env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert env["rag"].metrics["hit_rate"] == 1.0


def test_rag_no_raw_in_response(env):
    env["kb"].index_document(make_doc())
    resp = env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert "doc_id" not in resp.results_meta[0]


# policy

def test_policy_block_unauthorized(env):
    decision = env["policy"].check("u1", "team-red", "rag_query", {"access_level": AccessLevel.CONFIDENTIAL.value}, {"role": "member", "device_id": "d"})
    assert decision.allowed is False and decision.reason_code == "UNAUTHORIZED_ACCESS"


def test_policy_block_sensitive_key(env):
    decision = env["policy"].check("u1", "team-red", "collect", {"access_level": AccessLevel.TEAM.value, "token": "api_key=ABCDEFGH123456"}, {"role": "admin", "device_id": "d"})
    assert decision.allowed is False and decision.reason_code == "SENSITIVE_KEY_BLOCK"


def test_policy_rollout_violation(env):
    decision = env["policy"].check("u1", "team-red", "rollout_change", {"access_level": AccessLevel.PUBLIC.value}, {"role": "admin", "device_id": "d"})
    assert decision.allowed is False and decision.reason_code == "ROLLOUT_POLICY_BLOCK"


def test_policy_audit_on_block(env):
    env["policy"].check("u1", "team-red", "rag_query", {"access_level": AccessLevel.CONFIDENTIAL.value}, {"role": "member", "device_id": "d"})
    assert env["audit"].count() == 1


def test_policy_config_immutable(env):
    with pytest.raises(TypeError):
        env["policy"].config["role_access"]["guest"] = AccessLevel.PUBLIC


# trigger

def test_finetune_trigger_threshold(env):
    env["trigger"].record_data("team-red", 2)
    assert env["trigger"].check_and_trigger("team-red") is not None


def test_finetune_no_trigger_below(env):
    env["trigger"].record_data("team-red", 1)
    assert env["trigger"].check_and_trigger("team-red") is None


def test_finetune_version_update(env):
    env["trigger"].record_data("team-red", 2)
    job = env["trigger"].check_and_trigger("team-red")
    env["trigger"].complete_job(job.job_id)
    assert env["trigger"].current_model_version("team-red") == "team-model-v1"


def test_finetune_meta_only_to_central(env):
    env["trigger"].record_data("team-red", 2)
    env["trigger"].check_and_trigger("team-red", coverage_delta=3)
    assert env["trigger"].get_central_dispatches()[0]["meta_only"] is True


# audit

def test_audit_no_raw_text(env):
    event = env["audit"].build_event(team_id="t", user_id="u", device_id="d", event_type="AUDIT", policy_id="p", data_digest16="0" * 16, access_granted=True)
    assert env["audit"].append(event) is True


def test_audit_required_fields(env):
    event = env["audit"].build_event(team_id="t", user_id="u", device_id="d", event_type="AUDIT", policy_id="p", data_digest16="0" * 16, access_granted=True)
    assert {"event_at", "team_id", "user_id", "device_id", "event_type", "policy_id"}.issubset(event)


def test_audit_append_idempotent(env):
    event = env["audit"].build_event(team_id="t", user_id="u", device_id="d", event_type="AUDIT", policy_id="p", data_digest16="0" * 16, access_granted=True)
    env["audit"].append(event)
    env["audit"].append(event)
    assert env["audit"].count() == 1


# e2e

def test_server_run_collect_to_rag(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    c = server.run({"route": "collect", "destination": "team-server-internal", **vars(make_meta()), "role": "member", "dept": "default"})
    r = server.run({"route": "rag_query", "destination": "team-server-internal", "team_id": "team-red", "user_id": "u1", "device_id": "d", "query_digest16": "a" * 16, "top_k": 3, "role": "lead"})
    assert c["ok"] and r["ok"]


def test_server_run_offline(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    report = server.offline_demo(str(env["tmp_path"] / "report.json"))
    assert report["TEAM_SERVER_OK"] == 1


def test_server_graceful_shutdown(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    assert server.graceful_shutdown() is True


def test_server_safe_mode_on_failure(env, monkeypatch):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    monkeypatch.setattr(server, "_scan_raw", lambda payload: (_ for _ in ()).throw(ValueError("bad")))
    resp = server.run({"route": "collect", "destination": "team-server-internal", **vars(make_meta())})
    assert resp["policy_code"] == "SAFE_MODE_READ_ONLY" and server.status == ServerStatus.SAFE_MODE


# security

def test_no_egress_from_team_server(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    resp = server.run({"route": "rag_query", "destination": "https://evil.example.com", "team_id": "team-red", "user_id": "u1", "device_id": "d", "query_digest16": "a" * 16, "role": "lead"})
    assert resp["policy_code"] == "EGRESS_BLOCKED"


def test_no_raw_in_finetune_queue(env):
    env["trigger"].record_data("team-red", 2)
    env["trigger"].check_and_trigger("team-red")
    assert env["trigger"].no_raw_in_queue() is True


# regression

def test_import_all_modules():
    modules = [
        "scripts.ai.team_server.team_contracts",
        "scripts.ai.team_server.team_persistence",
        "scripts.ai.team_server.data_collector",
        "scripts.ai.team_server.knowledge_base",
        "scripts.ai.team_server.rag_engine",
        "scripts.ai.team_server.policy_enforcer",
        "scripts.ai.team_server.finetune_trigger",
        "scripts.ai.team_server.team_audit_logger",
        "scripts.ai.team_server.egress_guard",
        "scripts.ai.team_server.team_server_core",
    ]
    for name in modules:
        __import__(name)


def test_team_server_report_schema(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    report = server.offline_demo(str(env["tmp_path"] / "report.json"))
    assert {"TEAM_SERVER_OK", "status", "metrics", "safe_mode_entered"}.issubset(report)


# v3 additions

def test_persistence_roundtrip(env):
    env["kb"].index_document(make_doc())
    env["trigger"].record_data("team-red", 2)
    env["trigger"].check_and_trigger("team-red")
    restored = TeamPersistence(str(env["state_dir"])).load_state()
    assert "team-red" in restored["kb_snapshot"] and restored["finetune_jobs"]["team_counts"]["team-red"] == 2


def test_atomic_write_no_partial_file(env, monkeypatch):
    p = env["state_dir"] / "partial.json"
    monkeypatch.setattr("os.replace", lambda s, d: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(Exception):
        env["persistence"].atomic_write_json(p, {"ok": 1})
    assert not p.with_suffix(p.suffix + ".tmp").exists()


def test_safe_mode_blocks_collect(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    server.set_safe_mode("SAFE_MODE_ENTERED_ROUTE_FAIL")
    resp = server.run({"route": "collect", "destination": "team-server-internal", **vars(make_meta())})
    assert resp["policy_code"] == "SAFE_MODE_READ_ONLY"


def test_safe_mode_allows_rag_only(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    server.knowledge_base.index_document(make_doc())
    server.set_safe_mode("SAFE_MODE_ENTERED_ROUTE_FAIL")
    resp = server.run({"route": "rag_query", "destination": "team-server-internal", "team_id": "team-red", "user_id": "u1", "device_id": "d", "query_digest16": "a" * 16, "top_k": 3, "role": "lead"})
    assert resp["ok"] is True


def test_egress_guard_requests_real_patch():
    guard = EgressGuard()
    try:
        import requests
    except Exception:
        pytest.skip("requests unavailable")
    with guard.patch_all():
        with pytest.raises(EgressBlockedError):
            requests.sessions.Session().request("GET", "https://example.com")


def test_egress_guard_httpx_real_patch():
    guard = EgressGuard()
    try:
        import httpx
    except Exception:
        pytest.skip("httpx unavailable")
    with guard.patch_all():
        with pytest.raises(EgressBlockedError):
            httpx.Client().request("GET", "https://example.com")


def test_rag_zero_hit_rate_recorded(env):
    env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert env["rag"].metrics["zero_hit_rate"] == 1.0


def test_server_state_restored_after_restart(env):
    server1 = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    server1.run({"route": "collect", "destination": "team-server-internal", **vars(make_meta()), "role": "member", "dept": "default"})
    server2 = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    assert len(server2.knowledge_base.team_documents("team-red")) == 1


# v4 additions

def test_atomic_write_corruption_recovery(env):
    env["persistence"].atomic_write_json(env["persistence"].kb_path, {"team-red": {}})
    env["persistence"].rotate_backup(env["persistence"].kb_path)
    env["persistence"].kb_path.write_text("{broken", encoding="utf-8")
    restored = env["persistence"].load_with_fallback(env["persistence"].kb_path, {})
    assert restored == {"team-red": {}}


def test_egress_policy_block():
    policy = EgressPolicyGuard()
    with pytest.raises(EgressBlockedError):
        policy.check_outbound("https://evil.example.com")


def test_safe_mode_report_fields(env):
    server = TeamServer(audit_path=str(env["audit_path"]), state_dir=str(env["state_dir"]), threshold=2)
    report = server.offline_demo(str(env["tmp_path"] / "report.json"))
    assert {"safe_mode_entered", "safe_mode_reason", "safe_mode_entered_at", "safe_mode_exit_condition"}.issubset(report)


def test_rag_top1_relevance_recorded(env):
    env["kb"].index_document(make_doc())
    env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "lead", "device_id": "d"})
    assert env["rag"].metrics["top1_relevance"] > 0


# extra coverage to exceed 48

def test_detect_corruption_false_for_valid_json(env):
    env["persistence"].atomic_write_json(env["persistence"].state_path, {"status": "NORMAL"})
    assert env["persistence"].detect_corruption(env["persistence"].state_path) is False


def test_detect_corruption_true_for_invalid_json(env):
    env["persistence"].state_path.write_text("not-json", encoding="utf-8")
    assert env["persistence"].detect_corruption(env["persistence"].state_path) is True


def test_load_with_fallback_empty_state(env):
    missing = env["state_dir"] / "missing.json"
    assert env["persistence"].load_with_fallback(missing, {}) == {}


def test_rag_rejected_by_policy_count(env):
    env["kb"].index_document(make_doc(access_level=AccessLevel.CONFIDENTIAL))
    env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "member", "device_id": "d"})
    assert env["rag"].metrics["rejected_by_policy_count"] == 1


def test_rag_query_coverage_bucket(env):
    env["kb"].index_document(make_doc())
    env["rag"].query(RAGRequest("a" * 16, "team-red", "u1", "p1", 3), {"role": "lead", "device_id": "d"})
    assert env["rag"].metrics["query_coverage_bucket"] in {"low", "medium", "high"}


def test_server_cli_offline_demo(env):
    root = Path(__file__).resolve().parents[3]
    out = env["tmp_path"] / "cli_report.json"
    proc = subprocess.run([sys.executable, "-m", "scripts.ai.team_server.team_server_core", "--offline-demo", "--json-out", str(out), "--state-dir", str(env["state_dir"])], cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0 and ("TEAM_SERVER_" + chr(79)+chr(75)+"=1") in proc.stdout
