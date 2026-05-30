"""Codex P1 + P2 follow-on 회귀 방지 (2026-05-27).

#1 general_chat: chat 라우터가 sidecar(butler_sidecar.py)에 미등록이라 router_decision/
   usage_log의 sidecar-endpoint enum에서 POST /v1/chat/completions를 제거하고
   general_chat을 fallback(target_endpoint/endpoint=none, router는 fallback_required=true)
   으로 매핑했다. 옛 chat 엔드포인트 조합은 거부되어야 한다.

#2 expires_at: FormatChecker 없이 Draft7Validator(...).validate(...)로 검증해도
   2026-13-40T99:99:99Z 같은 invalid timestamp가 차단되도록 pattern range를 강화했다.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, FormatChecker
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas" / "connect_loop"
ROUTER = json.loads((SCHEMA_DIR / "router_decision.schema.json").read_text(encoding="utf-8"))
USAGE_LOG = json.loads((SCHEMA_DIR / "usage_log_v1_1.schema.json").read_text(encoding="utf-8"))
LEARNING_EVENT = json.loads((SCHEMA_DIR / "learning_event_v1.schema.json").read_text(encoding="utf-8"))


def _digest(v: str) -> str:
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


# ── #1 general_chat fallback (sidecar 미등록) ──

def _router(intent, box, endpoint, fallback):
    return {
        "request_id": "req-1", "intent_label": intent, "target_box_id": box,
        "target_endpoint": endpoint, "routing_confidence": 0.9, "reason_code": "X",
        "fallback_required": fallback, "policy_precheck": "allow", "schema_version": "router_decision.v1",
    }


def test_chat_completions_removed_from_router_endpoint_enum():
    assert "POST /v1/chat/completions" not in ROUTER["properties"]["target_endpoint"]["enum"]


def test_chat_completions_removed_from_usage_log_endpoint_enum():
    assert "POST /v1/chat/completions" not in USAGE_LOG["properties"]["endpoint"]["enum"]


def test_router_general_chat_to_none_fallback_passes():
    Draft7Validator(ROUTER).validate(_router("general_chat", "chat", "none", True))


def test_router_general_chat_to_old_chat_endpoint_fails():
    """옛 매핑(general_chat → POST /v1/chat/completions)은 이제 거부."""
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER).validate(_router("general_chat", "chat", "POST /v1/chat/completions", False))


def test_router_general_chat_without_fallback_fails():
    """general_chat은 fallback_required=true 강제."""
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER).validate(_router("general_chat", "chat", "none", False))


def _usage_log(intent, box, endpoint):
    # Codex P2 (2026-05-30): endpoint 'none'(fallback)은 real validation 불가 → contract_only/false.
    real = endpoint != "none"
    return {
        "log_id": "l1", "timestamp": "2026-05-29T00:00:00Z", "request_id": "r1",
        "device_id_digest": _digest("d"), "tenant_id_digest": _digest("t"), "department_id_digest": _digest("dep"),
        "request_digest": _digest("req"), "intent_label": intent, "box_id": box, "endpoint": endpoint,
        "routing_confidence": 0.9,
        "integration_mode": "real" if real else "contract_only",
        "real_validation_done": real,
        "result_digest": _digest("res"), "source_digests": [_digest("s")], "policy_decision": "allow",
        "policy_reason_code": "OK", "latency_ms": 10.0, "external_send_zero": True, "raw_text_logged": False,
        "learning_candidate": True, "learning_event_created": False, "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.middleware", "schema_hash": _digest("s"), "schema_version": "usage_log.v1.1",
    }


def test_usage_log_general_chat_to_none_passes():
    Draft7Validator(USAGE_LOG).validate(_usage_log("general_chat", "chat", "none"))


def test_usage_log_general_chat_to_old_chat_endpoint_fails():
    with pytest.raises(ValidationError):
        Draft7Validator(USAGE_LOG).validate(_usage_log("general_chat", "chat", "POST /v1/chat/completions"))


# ── #3 endpoint 'none'(fallback)은 real validation 으로 위장 불가 (Codex P2 재리뷰 2026-05-30) ──

@pytest.mark.parametrize("intent,box", [("general_chat", "chat"), ("unknown", "none")])
def test_usage_log_none_endpoint_real_mode_fails(intent, box):
    bad = _usage_log(intent, box, "none")
    bad["integration_mode"] = "real"
    with pytest.raises(ValidationError):
        Draft7Validator(USAGE_LOG).validate(bad)


@pytest.mark.parametrize("intent,box", [("general_chat", "chat"), ("unknown", "none")])
def test_usage_log_none_endpoint_real_validation_done_true_fails(intent, box):
    bad = _usage_log(intent, box, "none")
    bad["real_validation_done"] = True
    with pytest.raises(ValidationError):
        Draft7Validator(USAGE_LOG).validate(bad)


@pytest.mark.parametrize("intent,box", [("general_chat", "chat"), ("unknown", "none")])
def test_usage_log_none_endpoint_contract_only_passes(intent, box):
    Draft7Validator(USAGE_LOG).validate(_usage_log(intent, box, "none"))


# ── #2 expires_at pattern range ──

_LE_BASE = {
    "learning_event_id": "le-1", "source_usage_log_id": "log-1", "created_at": "2026-05-29T10:00:00Z",
    "status": "APPROVED", "tenant_scope": "team", "learning_type": "accounting_classify",
    "raw_input_saved": False, "raw_output_saved": False, "approved_text_ref": "vault://x",
    "approved_text_digest": _digest("a"), "sanitized_summary_digest": _digest("b"), "sanitized_summary_saved": False,
    "label": {"intent_label": "accounting_classify", "target_box_id": "5", "quality": "good"},
    "policy_approval": {"decision": "approved", "approver_role": "manager", "reason_code": "OK"},
    "dlp_result": {"passed": True, "pii_detected": False, "secret_detected": False, "policy_violation": False},
    "retention_days": 90, "expires_at": "2026-08-27T10:00:00Z", "verified_for_training": True,
    "schema_version": "learning_event.v1",
}


def _le_expires(ts: str) -> dict:
    d = copy.deepcopy(_LE_BASE)
    d["expires_at"] = ts
    return d


@pytest.mark.parametrize("bad_ts", [
    "2026-13-15T10:00:00Z",  # month > 12
    "2026-00-15T10:00:00Z",  # month 00
    "2026-05-32T10:00:00Z",  # day > 31
    "2026-05-00T10:00:00Z",  # day 00
    "2026-05-15T25:00:00Z",  # hour > 23
    "2026-05-15T10:60:00Z",  # minute > 59
    "2026-05-15T10:00:60Z",  # second > 59
    "2026-13-40T99:99:99Z",  # Codex 예시
    "2026-05-15T10:00:00+99:99",  # offset hour/minute invalid
    "2026-05-15T10:00:00+24:00",  # offset hour > 23
    "2026-05-15T10:00:00+09:60",  # offset minute > 59
])
def test_expires_at_invalid_range_rejected(bad_ts):
    with pytest.raises(ValidationError):
        Draft7Validator(LEARNING_EVENT).validate(_le_expires(bad_ts))


@pytest.mark.parametrize("good_ts", [
    "2026-05-15T10:00:00Z",
    "2026-12-31T23:59:59Z",
    "2026-01-01T00:00:00Z",
    "2026-05-15T10:00:00.123Z",
    "2026-05-15T10:00:00+09:00",
    "2026-05-15T10:00:00+09:30",
    "2026-05-15T10:00:00-05:00",
    "2026-05-15T10:00:00+05:45",  # Nepal (+05:45) — 정당한 :45 offset minute 통과 확인 (allowlist 미도입 근거)
])
def test_expires_at_valid_passes(good_ts):
    Draft7Validator(LEARNING_EVENT).validate(_le_expires(good_ts))


def test_expires_at_with_format_checker_strict():
    Draft7Validator(LEARNING_EVENT, format_checker=FormatChecker()).validate(_le_expires("2026-05-15T10:00:00Z"))
    with pytest.raises(ValidationError):
        Draft7Validator(LEARNING_EVENT, format_checker=FormatChecker()).validate(_le_expires("2026-13-40T99:99:99Z"))
