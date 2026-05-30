from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from butler_pc_core.connect_loop.box1_router import RouterRuntimeContext, RuleBasedBox1Router


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


CHAT_REQUEST = {
    "request_id": "req-prc-sec-0001",
    "session_id_digest": _digest("session"),
    "tenant_id_digest": _digest("tenant"),
    "device_id": "device-local-001",
    "user_role": "employee",
    "department_id_digest": _digest("department"),
    "text_ref": "device_local_only",
    "text_digest": _digest("input"),
    "attachments": [],
    "created_at": "2026-05-30T09:00:00Z",
    "schema_version": "chat_request.v1",
}


def _decision(marker: str) -> dict:
    return RuleBasedBox1Router().decide(
        copy.deepcopy(CHAT_REQUEST),
        RouterRuntimeContext(runtime_text=f"{marker} 이전 과거 문서 자료를 찾아줘 검색", policy_precheck="allow"),
    )


def test_runtime_text_not_in_decision():
    marker = "DEVICE_ONLY_SENTINEL_20260530"
    decision_text = json.dumps(_decision(marker), ensure_ascii=False)
    assert marker not in decision_text


def test_runtime_text_not_in_evidence(tmp_path: Path):
    marker = "EVIDENCE_SENTINEL_20260530"
    decision = _decision(marker)
    evidence = tmp_path / "router_decision.json"
    evidence.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")
    assert marker not in evidence.read_text(encoding="utf-8")


def test_no_raw_field_keys():
    keys = set(_decision("FIELD_SENTINEL").keys())
    assert not any(key.startswith("raw_") for key in keys)
    assert "runtime_text" not in keys


def test_no_external_network_imports():
    root = Path(__file__).resolve().parents[2] / "butler_pc_core" / "connect_loop"
    joined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    denied = ["httpx.", "aiohttp", "urllib.request", "socket."]
    assert not any(item in joined for item in denied)


def test_no_schema_mutation_during_routing():
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "connect_loop" / "router_decision.schema.json"
    before = _digest(schema_path.read_text(encoding="utf-8"))
    _decision("SCHEMA_SENTINEL")
    after = _digest(schema_path.read_text(encoding="utf-8"))
    assert after == before
