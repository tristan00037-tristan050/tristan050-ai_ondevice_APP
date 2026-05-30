from __future__ import annotations

import json
import hashlib
from pathlib import Path

from jsonschema import Draft7Validator

from butler_pc_core.connect_loop.box1_router import (
    RouterRuntimeContext,
    RuleBasedBox1Router,
    canonical_sha256,
    runtime_text_digest_ok,
)
from butler_pc_core.connect_loop.schema_validator import load_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO_ROOT / "butler_pc_core" / "connect_loop"
_ROUTER_DECISION_SCHEMA = load_schema("router_decision.schema.json")


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
    runtime_text = f"{private_input} 거래내역 계정과목 회계분류와 분개"
    decision = RuleBasedBox1Router().decide(
        _chat_request(text_digest=canonical_sha256(runtime_text)),
        RouterRuntimeContext(runtime_text=runtime_text, policy_precheck="allow"),
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


# ── Codex P2 (2026-05-30): runtime_text ↔ text_digest fail-closed 대조 ──

_ACCOUNTING_TEXT = "거래내역 계정과목 회계분류와 분개를 해줘"


def test_text_digest_match_allows_routing():
    """runtime_text 의 digest 가 chat_request.text_digest 와 일치하면 정상 라우팅."""
    chat_request = _chat_request(text_digest=canonical_sha256(_ACCOUNTING_TEXT))
    decision = RuleBasedBox1Router().decide(
        chat_request, RouterRuntimeContext(runtime_text=_ACCOUNTING_TEXT, policy_precheck="allow")
    )
    assert decision["intent_label"] == "accounting_classify"
    assert decision["target_endpoint"] == "POST /accounting/classify"
    assert decision["reason_code"] != "TEXT_DIGEST_MISMATCH"
    Draft7Validator(_ROUTER_DECISION_SCHEMA).validate(decision)


def test_text_digest_mismatch_forces_unknown():
    """digest 불일치(잘못 짝지어진 runtime context) → unknown/none/fallback/TEXT_DIGEST_MISMATCH."""
    chat_request = _chat_request(text_digest=canonical_sha256("전혀 다른 큐 대기 요청 텍스트"))
    decision = RuleBasedBox1Router().decide(
        chat_request, RouterRuntimeContext(runtime_text=_ACCOUNTING_TEXT, policy_precheck="allow")
    )
    assert decision["intent_label"] == "unknown"
    assert decision["target_box_id"] == "none"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True
    assert decision["routing_confidence"] == 0.0
    assert decision["reason_code"] == "TEXT_DIGEST_MISMATCH"
    # router_decision self-validate → reason_code 계약 정합 확인
    Draft7Validator(_ROUTER_DECISION_SCHEMA).validate(decision)


def test_no_text_digest_skips_check():
    """text_digest 부재 시 대조 스킵(정의된 동작=None). (스키마상 required → 방어적 분기.)"""
    assert runtime_text_digest_ok("어떤 디바이스 로컬 텍스트", {}) is None
    assert runtime_text_digest_ok(None, {"text_digest": canonical_sha256("x")}) is None


def test_digest_check_uses_same_normalization():
    """생성·검증이 동일 canonical_sha256 을 쓰므로 동일 원문은 false mismatch 0 (공백/줄바꿈/유니코드 포함)."""
    for text in [
        _ACCOUNTING_TEXT,
        "  앞뒤 공백 있는 거래내역 계정과목 회계분류 분개  ",
        "줄바꿈\n포함 거래내역 계정과목 회계분류 분개",
        "混合 유니코드 거래내역 계정과목 회계분류 분개 テキスト",
    ]:
        chat_request = _chat_request(text_digest=canonical_sha256(text))
        assert runtime_text_digest_ok(text, chat_request) is True
        decision = RuleBasedBox1Router().decide(
            chat_request, RouterRuntimeContext(runtime_text=text, policy_precheck="allow")
        )
        assert decision["reason_code"] != "TEXT_DIGEST_MISMATCH"
