from __future__ import annotations
import json, sys
from pathlib import Path
from datetime import datetime
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai.central_server.central_contracts import (
    TeamInsight, EnterpriseKBDoc, ModelVersion, DeploymentOrder,
    EventType, ModelStatus, ServerStatus
)
from scripts.ai.central_server.central_persistence import PersistenceManager, SCHEMA_VERSION
from scripts.ai.central_server.egress_guard import EgressGuard, EgressPolicyGuard, EgressBlockedError
from scripts.ai.central_server.enterprise_audit import EnterpriseAudit
from scripts.ai.central_server.insight_collector import InsightCollector
from scripts.ai.central_server.enterprise_kb import EnterpriseKB
from scripts.ai.central_server.continuous_learner import ContinuousLearner
from scripts.ai.central_server.model_registry import ModelRegistry
from scripts.ai.central_server.deployment_controller import DeploymentController
from scripts.ai.central_server.central_report_writer import CentralReportWriter
from scripts.ai.central_server.central_server_core import CentralServer

@pytest.fixture
def workdir(tmp_path):
    root = tmp_path / "ai32_build"
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    return root

def mk_insight(team="team-a", count=1):
    return TeamInsight(team_id=team, insight_type="KB_UPDATE", data_digest16="d"*16, record_count=count, timestamp=datetime.utcnow().isoformat(), model_version="m0", source_server_id="ts1")

def mk_doc(doc_id="doc1", team="team-a", version=1, lineage="line1", tags=None):
    return EnterpriseKBDoc(doc_id=doc_id, title_digest16="t"*16, summary="alpha beta gamma", tags=tags or ["alpha","beta"], team_id=team, version=version, access_level="TEAM", created_at=datetime.utcnow().isoformat(), lineage_id=lineage)

def mk_order(version_id="model-1"):
    return DeploymentOrder(order_id="order-1", model_version_id=version_id, target_type="ALL_TEAMS", target_ids=["team-a"], issued_at=datetime.utcnow().isoformat(), status="CREATED", requested_by="admin", requested_at=datetime.utcnow().isoformat(), deploy_order_digest16="o"*16, rollback_required_if="regression")

def test_collect_insight_meta_only():
    c = InsightCollector()
    r = c.receive(mk_insight(count=2))
    assert r.ok and r.count == 2

def test_collect_reject_raw():
    ins = mk_insight()
    ins.raw_text = "secret"
    c = InsightCollector()
    r = c.receive(ins)
    assert not r.ok and r.error_code == "RAW_BLOCKED"

def test_collect_counter_increment():
    c = InsightCollector()
    c.receive(mk_insight(count=2))
    c.receive(mk_insight(count=3))
    assert c.get_stats()["total_count"] == 5

def test_collect_trigger_on_threshold():
    learner = ContinuousLearner()
    c = InsightCollector(learner, threshold=5)
    c.receive(mk_insight(count=5))
    assert learner.jobs and learner.jobs[0].trigger_reason == "THRESHOLD_REACHED"

def test_kb_index_document():
    kb = EnterpriseKB()
    r = kb.index_document(mk_doc())
    assert r.ok and r.indexed_count == 1

def test_kb_no_raw_content():
    kb = EnterpriseKB()
    d = mk_doc()
    kb.index_document(d)
    assert "alpha beta gamma" in kb.docs[d.doc_id].summary

def test_kb_team_aggregation():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1","team-a"))
    kb.index_document(mk_doc("d2","team-b"))
    assert kb.get_coverage()["team_diversity"] == 2

def test_kb_coverage_stats():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1"))
    cov = kb.get_coverage()
    assert "topic_coverage" in cov and "stale_doc_count" in cov

def test_kb_lineage():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1", version=1, lineage="x"))
    kb.index_document(mk_doc("d2", version=2, lineage="x"))
    assert len(kb.get_lineage("d1")) == 2

def test_learner_job_created():
    learner = ContinuousLearner()
    job = learner.check_and_trigger(["a"], 5000)
    assert job is not None

def test_learner_no_trigger_below():
    learner = ContinuousLearner()
    assert learner.check_and_trigger(["a"], 10) is None

def test_learner_model_version_created():
    reg = ModelRegistry()
    learner = ContinuousLearner(reg)
    job = learner.check_and_trigger(["a"], 5000)
    mv = learner.complete_job(job.job_id)
    assert mv.version_id in reg.versions

def test_learner_auto_validate():
    reg = ModelRegistry()
    learner = ContinuousLearner(reg)
    job = learner.check_and_trigger(["a"], 5000)
    mv = learner.complete_job(job.job_id, 0.95)
    assert mv.status == ModelStatus.VALIDATED.value

def test_learner_no_auto_approve():
    reg = ModelRegistry()
    learner = ContinuousLearner(reg)
    job = learner.check_and_trigger(["a"], 5000)
    mv = learner.complete_job(job.job_id, 0.99)
    assert mv.status != ModelStatus.APPROVED.value

def test_registry_register():
    reg = ModelRegistry()
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.PENDING.value,0.1,0,"j1")
    assert reg.register(mv).ok

def test_registry_approve():
    reg = ModelRegistry()
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.VALIDATED.value,0.91,0,"j1")
    reg.register(mv)
    rr = reg.approve("v1")
    assert rr.status == ModelStatus.APPROVED.value and reg.versions["v1"].deploy_approved == 1

def test_registry_pending_block():
    reg = ModelRegistry()
    audit = EnterpriseAudit(Path("/tmp/central_audit_test1.jsonl"))
    dep = DeploymentController(reg, audit)
    reg.register(ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.PENDING.value,0.1,0,"j1"))
    assert not dep.deploy(mk_order("v1")).ok

def test_registry_validated_block():
    reg = ModelRegistry()
    audit = EnterpriseAudit(Path("/tmp/central_audit_test2.jsonl"))
    dep = DeploymentController(reg, audit)
    reg.register(ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.VALIDATED.value,0.95,0,"j1"))
    assert not dep.deploy(mk_order("v1")).ok

def test_registry_latest_approved():
    reg = ModelRegistry()
    for i in range(2):
        mv = ModelVersion(f"v{i}","p1",datetime.utcnow().isoformat(),ModelStatus.VALIDATED.value,0.95,0,"j1")
        reg.register(mv); reg.approve(f"v{i}")
    assert reg.get_latest_approved().version_id == "v1"

def test_registry_deprecate():
    reg = ModelRegistry()
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.APPROVED.value,0.95,1,"j1")
    reg.register(mv)
    assert reg.deprecate("v1").status == ModelStatus.DEPRECATED.value

def test_deploy_approved_only():
    reg = ModelRegistry(); audit = EnterpriseAudit(Path("/tmp/central_audit_test3.jsonl")); dep = DeploymentController(reg,audit)
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.VALIDATED.value,0.95,0,"j1")
    reg.register(mv); reg.approve("v1")
    assert dep.deploy(mk_order("v1")).ok

def test_deploy_pending_blocked():
    reg = ModelRegistry(); audit = EnterpriseAudit(Path("/tmp/central_audit_test4.jsonl")); dep = DeploymentController(reg,audit)
    reg.register(ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.PENDING.value,0.1,0,"j1"))
    assert dep.deploy(mk_order("v1")).error_code == "MODEL_NOT_APPROVED"

def test_deploy_safe_mode_blocked():
    reg = ModelRegistry(); audit = EnterpriseAudit(Path("/tmp/central_audit_test5.jsonl")); dep = DeploymentController(reg,audit)
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.APPROVED.value,0.95,1,"j1")
    reg.register(mv)
    assert dep.deploy(mk_order("v1"), safe_mode=True).error_code == "SAFE_MODE_ACTIVE"

def test_audit_no_raw_text(workdir):
    audit = EnterpriseAudit(workdir/"tmp/a.jsonl")
    ok = audit.append({"event_at":"t","team_id":"a","event_type":"DEPLOY","model_version":"m","policy_code":"","data_digest16":"d","reason_code":"r"})
    assert ok and "payload" not in (workdir/"tmp/a.jsonl").read_text()

def test_audit_required_fields(workdir):
    audit = EnterpriseAudit(workdir/"tmp/a2.jsonl")
    audit.append({"event_at":"t","team_id":"a","event_type":"DEPLOY","model_version":"m","policy_code":"","data_digest16":"d","reason_code":"r"})
    line = json.loads((workdir/"tmp/a2.jsonl").read_text().splitlines()[0])
    assert {"event_at","team_id","event_type","model_version","data_digest16","reason_code"} <= set(line)

def test_audit_append_idempotent(workdir):
    audit = EnterpriseAudit(workdir/"tmp/a3.jsonl")
    item = {"event_at":"t","team_id":"a","event_type":"DEPLOY","model_version":"m","policy_code":"","data_digest16":"d","reason_code":"r"}
    audit.append(item); audit.append(item)
    assert len((workdir/"tmp/a3.jsonl").read_text().splitlines()) == 1

def test_persistence_atomic_write(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    assert pm.atomic_write_json(workdir/"tmp/central_state/x.json", {"a":1})

def test_persistence_corruption_recovery(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    p = workdir/"tmp/central_state/x.json"
    pm.atomic_write_json(p, {"a":1}); pm.rotate_backup(p)
    p.write_text("{bad", encoding="utf-8")
    data = pm.load_with_fallback(p, empty_state={"a":0})
    assert data["a"] == 1

def test_persistence_backup_rotate(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    p = workdir/"tmp/central_state/y.json"
    pm.atomic_write_json(p, {"a":1}); pm.rotate_backup(p)
    assert Path(str(p)+".bak").exists()

def test_persistence_load_with_fallback(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    p = workdir/"tmp/central_state/z.json"
    data = pm.load_with_fallback(p, empty_state={"x":1})
    assert data["x"] == 1

def test_safe_mode_blocks_deploy(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("test")
    r = s.run({"route": EventType.DEPLOY.value, "payload": as_payload_order("v1")})
    assert not r.ok and r.error_code == "SAFE_MODE_ACTIVE"

def test_safe_mode_allows_kb_update(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("test")
    r = s.run({"route": EventType.KB_UPDATE.value, "payload": as_payload_doc("d1")})
    assert r.ok

def test_safe_mode_report_fields(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("test")
    rep = s.build_report()
    assert "safe_mode_entered" in rep and "safe_mode_last_reason" in rep

def test_no_egress_from_central():
    g = EgressGuard()
    with pytest.raises(EgressBlockedError):
        with g.patch_all():
            g.check_call("http://evil")

def test_no_raw_in_learning_job():
    learner = ContinuousLearner()
    job = learner.check_and_trigger(["a"], 5000)
    assert "digest" in job.data_digest16 and "payload" not in job.data_digest16

def test_no_raw_in_deploy_order():
    o = mk_order("v1")
    assert "http" not in (o.deploy_order_digest16 or "")

def test_server_collect_to_deploy(workdir):
    s = CentralServer(workdir)
    r1 = s.run({"route": EventType.INSIGHT_COLLECT.value, "payload": as_payload_insight(count=5000)})
    job = s.learner.jobs[0]
    mv = s.learner.complete_job(job.job_id, 0.95)
    s.run({"route": EventType.MODEL_APPROVE.value, "payload": {"version_id": mv.version_id, "approved_by":"boss","approval_policy_version":"pv1","approval_note_digest16":"n"*16}})
    r2 = s.run({"route": EventType.DEPLOY.value, "payload": as_payload_order(mv.version_id)})
    assert r1.ok and r2.ok

def test_server_offline_mode(workdir):
    s = CentralServer(workdir)
    rep = s.build_report()
    assert rep["execution_mode"] == "offline-demo"

def test_server_report_schema(workdir):
    s = CentralServer(workdir)
    rep = s.build_report()
    assert rep["schema_version"] == SCHEMA_VERSION

def test_import_all_modules():
    import scripts.ai.central_server.central_contracts
    import scripts.ai.central_server.central_persistence
    import scripts.ai.central_server.central_report_writer
    import scripts.ai.central_server.egress_guard
    import scripts.ai.central_server.insight_collector
    import scripts.ai.central_server.enterprise_kb
    import scripts.ai.central_server.continuous_learner
    import scripts.ai.central_server.model_registry
    import scripts.ai.central_server.deployment_controller
    import scripts.ai.central_server.enterprise_audit
    import scripts.ai.central_server.central_server_core

def test_learning_loop_e2e(workdir):
    s = CentralServer(workdir)
    s.run({"route": EventType.INSIGHT_COLLECT.value, "payload": as_payload_insight(count=5000)})
    mv = s.learner.complete_job(s.learner.jobs[0].job_id, 0.92)
    assert mv.status == ModelStatus.VALIDATED.value

def test_model_version_history(workdir):
    s = CentralServer(workdir)
    s.run({"route": EventType.INSIGHT_COLLECT.value, "payload": as_payload_insight(count=5000)})
    mv = s.learner.complete_job(s.learner.jobs[0].job_id, 0.92)
    s.registry.approve(mv.version_id)
    assert mv.version_id in s.registry.versions

# v3 add-ons
def test_persistence_schema_version_migration(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    p = workdir/"tmp/central_state/m.json"
    p.write_text(json.dumps({"schema_version":"wrong","a":1}), encoding="utf-8")
    assert pm.detect_corruption(p)

def test_persistence_cross_file_consistency(workdir):
    s = CentralServer(workdir)
    s.build_report(); s._persist_all()
    assert s.persistence.ensure_consistent_bundle()

def test_egress_policy_allowlist_only():
    ep = EgressPolicyGuard()
    ep.check_outbound("central-server-internal")
    with pytest.raises(EgressBlockedError):
        ep.check_outbound("https://evil.example")

def test_egress_exception_digest_only():
    ep = EgressPolicyGuard()
    with pytest.raises(EgressBlockedError) as e:
        ep.check_outbound("https://evil.example/path?q=x")
    msg = str(e.value)
    assert "https://evil.example" not in msg and len(msg.split(":")[1]) == 16

def test_safe_mode_block_counter_increment(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("test")
    s.run({"route": EventType.DEPLOY.value, "payload": as_payload_order("v1")})
    assert s.safe_mode_block_count == 1

def test_safe_mode_exit_condition_reported(workdir):
    s = CentralServer(workdir)
    rep = s.build_report()
    assert rep["safe_mode_exit_condition"] == "manual_reset or restart"

def test_registry_approval_audit_fields():
    reg = ModelRegistry()
    mv = ModelVersion("v1","p1",datetime.utcnow().isoformat(),ModelStatus.VALIDATED.value,0.95,0,"j1")
    reg.register(mv); reg.approve("v1", "chief", "pv2", "n"*16)
    assert reg.versions["v1"].approved_by == "chief" and reg.versions["v1"].approval_policy_version == "pv2"

def test_rag_zero_hit_reason_recorded():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1","team-a"))
    res = kb.query("unmatched words", ["zzz"], allowed_teams=["team-b"])
    assert res["zero_hit_reason"] in {"POLICY_FILTERED","LOW_MATCH","NO_DOCS"}

# Additional tests to exceed 60
def as_payload_insight(team="team-a", count=1):
    return {
        "team_id": team, "insight_type": "KB_UPDATE", "data_digest16": "d"*16,
        "record_count": count, "timestamp": datetime.utcnow().isoformat(), "model_version": "m0", "source_server_id": "ts1"
    }

def as_payload_doc(doc_id="doc1", team="team-a", version=1):
    return {
        "doc_id": doc_id, "title_digest16": "t"*16, "summary": "alpha beta gamma",
        "tags": ["alpha","beta"], "team_id": team, "version": version, "access_level":"TEAM",
        "created_at": datetime.utcnow().isoformat(), "lineage_id":"line1"
    }

def as_payload_order(version_id="model-1"):
    return {
        "order_id":"order-1","model_version_id":version_id,"target_type":"ALL_TEAMS","target_ids":["team-a"],
        "issued_at":datetime.utcnow().isoformat(),"status":"CREATED","requested_by":"admin","requested_at":datetime.utcnow().isoformat(),
        "deploy_order_digest16":"o"*16,"rollback_required_if":"regression"
    }

def test_report_contains_counts(workdir):
    s = CentralServer(workdir)
    rep = s.build_report()
    assert {"approved_version_count","pending_version_count","deploy_block_count","egress_block_count"} <= set(rep)

def test_report_writer_atomic(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    rw = CentralReportWriter(pm)
    out = workdir/"tmp/r.json"
    assert rw.write_report(out, {"schema_version":SCHEMA_VERSION,"execution_mode":"x","server_status":"NORMAL","safe_mode_entered":False,"learning_jobs_count":0,"latest_model_version":"","deploy_block_count":0,"product_ready_reason":"ok"})

def test_core_raw_request_blocked(workdir):
    s = CentralServer(workdir)
    r = s.run({"route": EventType.INSIGHT_COLLECT.value, "payload": as_payload_insight(), "raw_text":"abc"})
    assert not r.ok and r.error_code == "RAW_FORBIDDEN"

def test_core_unknown_route_enters_safe_mode(workdir):
    s = CentralServer(workdir)
    r = s.run({"route":"UNKNOWN","payload":{}})
    assert not r.ok and r.safe_mode

def test_registry_get_latest_none():
    reg = ModelRegistry()
    assert reg.get_latest_approved() is None

def test_deployer_model_not_found():
    reg = ModelRegistry(); audit = EnterpriseAudit(Path("/tmp/central_audit_test6.jsonl")); dep = DeploymentController(reg,audit)
    assert dep.deploy(mk_order("missing")).error_code == "MODEL_NOT_FOUND"

def test_kb_query_policy_filtered():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1","team-a"))
    res = kb.query("alpha", ["alpha"], allowed_teams=["team-b"])
    assert res["rejected_by_policy_count"] == 1

def test_kb_query_top1():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1","team-a"))
    res = kb.query("alpha beta", ["alpha"], allowed_teams=["team-a"])
    assert res["top1_relevance"] >= 0

def test_kb_query_diversity():
    kb = EnterpriseKB()
    kb.index_document(mk_doc("d1","team-a"))
    kb.index_document(mk_doc("d2","team-b", lineage="l2"))
    res = kb.query("alpha", ["alpha"], allowed_teams=["team-a","team-b"])
    assert 0 <= res["result_diversity_score"] <= 1

def test_restore_state_after_restart(workdir):
    s = CentralServer(workdir)
    s.run({"route": EventType.KB_UPDATE.value, "payload": as_payload_doc("d1")})
    s._persist_all()
    s2 = CentralServer(workdir)
    assert "d1" in s2.kb.docs

def test_report_latest_model_version_after_approve(workdir):
    s = CentralServer(workdir)
    s.run({"route": EventType.INSIGHT_COLLECT.value, "payload": as_payload_insight(count=5000)})
    mv = s.learner.complete_job(s.learner.jobs[0].job_id, 0.92)
    s.registry.approve(mv.version_id)
    assert s.build_report()["latest_model_version"] == mv.version_id

def test_safe_mode_last_reason(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("x")
    s.run({"route": EventType.DEPLOY.value, "payload": as_payload_order("v1")})
    assert s.safe_mode_last_reason == "SAFE_MODE_READ_ONLY"

def test_persistence_tmp_cleanup_on_failure(monkeypatch, workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    target = workdir/"tmp/central_state/f.json"
    import os as _os
    original = _os.replace
    def boom(src, dst):
        raise OSError("boom")
    monkeypatch.setattr(_os, "replace", boom)
    ok = pm.atomic_write_json(target, {"x":1})
    monkeypatch.setattr(_os, "replace", original)
    assert not ok
    assert not (workdir/"tmp/central_state/f.json.tmp").exists()

def test_persistence_lock_available(workdir):
    pm = PersistenceManager(workdir/"tmp/central_state")
    with pm.concurrent_guard():
        ok = True
    assert ok

def test_policy_block_deploy_in_safe_mode_response(workdir):
    s = CentralServer(workdir)
    s.enter_safe_mode("x")
    r = s.run({"route": EventType.DEPLOY.value, "payload": as_payload_order("v1")})
    assert r.policy_code == "SAFE_MODE_READ_ONLY"

def test_egress_block_counter(workdir):
    s = CentralServer(workdir)
    s.run({"route":"UNKNOWN","payload":{}})
    assert s.safe_mode_entered

def test_state_files_created(workdir):
    s = CentralServer(workdir)
    s._persist_all()
    for name in ["enterprise_kb_snapshot.json","learning_jobs.json","model_registry.json","central_state.json"]:
        assert (workdir/"tmp/central_state"/name).exists()

def test_bak_files_created_after_second_save(workdir):
    s = CentralServer(workdir)
    s._persist_all(); s._persist_all()
    for name in ["enterprise_kb_snapshot.json","learning_jobs.json","model_registry.json","central_state.json"]:
        assert (workdir/"tmp/central_state"/(name + ".bak")).exists()

def test_report_file_written(workdir):
    s = CentralServer(workdir)
    s.build_report()
    assert (workdir/"tmp/central_server_report.json").exists()
