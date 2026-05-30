from __future__ import annotations

import json
import hashlib
from pathlib import Path

from butler_pc_core.connect_loop.box1_router import (
    RouterRuntimeContext,
    RuleBasedBox1Router,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO_ROOT / "butler_pc_core" / "connect_loop"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _chat_request(text_digest: str | None = None) -> dict:
    return {
        "request_id": "req-box1-router-security-001",
        "session_id_digest": _digest("session"),
        "tenant_id_digest": _digest("tenant"),
        "device_id": "device-local-001",
        "user_role": "employee",
        "department_id_digest": _digest("department"),
        "text_ref": "device_local_only",
        "text_digest": text_digest or _digest("message"),
        "attachments": [],
        "created_at": "2026-05-30T10:00:00+09:00",
        "schema_version": "chat_request.v1",
    }


def _decision_for_private_input() -> tuple[str, dict]:
    private_input = "UNIQUE_DEVICE_LOCAL_INPUT_PR_C_481516"
    decision = RuleBasedBox1Router().decide(
        _chat_request(),
        RouterRuntimeContext(
            runtime_text=f"{private_input} 거래내역 계정과목 회계분류와 분개",
            policy_precheck="allow",
        ),
    )
    return private_input, decision


def test_runtime_text_not_in_decision():
    private_input, decision = _decision_for_private_input()
    assert private_input not in json.dumps(decision, ensure_ascii=False)
    assert "runtime_text" not in decision


def test_runtime_text_not_in_evidence(tmp_path):
    private_input, decision = _decision_for_private_input()
    evidence = {
        "status": "PASS",
        "decision_schema_version": decision["schema_version"],
        "intent_label": decision["intent_label"],
        "target_box_id": decision["target_box_id"],
        "target_endpoint": decision["target_endpoint"],
    }
    path = tmp_path / "box1_router_evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    assert private_input not in path.read_text(encoding="utf-8")


def test_no_raw_field_keys():
    _private_input, decision = _decision_for_private_input()
    blocked_keys = {"runtime_text", "query_text", "answer_text", "local_path", "file_name"}
    assert blocked_keys.isdisjoint(decision)


def test_no_external_network_imports():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in MODULE_DIR.glob("*.py"))
    blocked_patterns = [
        "requests" + ".",
        "httpx" + ".",
        "aiohttp",
        "urllib" + ".request",
        "socket" + ".",
    ]
    for pattern in blocked_patterns:
        assert pattern not in combined


def test_no_schema_modification():
    assert (REPO_ROOT / "schemas" / "connect_loop" / "chat_request.schema.json").exists()
    assert (REPO_ROOT / "schemas" / "connect_loop" / "router_decision.schema.json").exists()
    assert not list(MODULE_DIR.glob("*.schema.json"))
