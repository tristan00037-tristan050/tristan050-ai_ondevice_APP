"""Codex P1 + P2 정정 회귀 방지 (2026-05-27).

router_decision.schema의 intent→box(/endpoint) 매핑을 두 곳에 mirror:
  #1 learning_event_v1.schema  — label.intent_label → label.target_box_id
     (training pipeline 유일 shape에서 mislabel 차단)
  #2 usage_log_v1_1.schema     — intent_label → box_id / endpoint
     (router_decision validation 없이 독립 ingest될 때 audit record 오염 차단)

learning_type은 intent_label과 권위 매핑이 없고 enum 집합이 달라 일관성 검사에
포함하지 않는다(추정 방지).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas" / "connect_loop"
LEARNING_EVENT_SCHEMA = json.loads((SCHEMA_DIR / "learning_event_v1.schema.json").read_text(encoding="utf-8"))
USAGE_LOG_SCHEMA = json.loads((SCHEMA_DIR / "usage_log_v1_1.schema.json").read_text(encoding="utf-8"))

# router_decision 실측 매핑표 (intent → box_id / endpoint).
INTENT_MAP = {
    "memory_search": ("helper1", "POST /v1/helpers/1/search"),
    "form_convert": ("2", "POST /v1/cards/2/rewrite"),
    "draft_write": ("3", "POST /v1/cards/3/draft"),
    "accounting_classify": ("5", "POST /accounting/classify"),
    "general_chat": ("chat", "none"),
    "unknown": ("none", "none"),
}


def _digest(v: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


_LE_BASE = {
    "learning_event_id": "le-0001", "source_usage_log_id": "log-0001",
    "created_at": "2026-05-29T10:00:00Z", "status": "APPROVED", "tenant_scope": "team",
    "learning_type": "accounting_classify", "raw_input_saved": False, "raw_output_saved": False,
    "approved_text_ref": "vault://approved/le-0001", "approved_text_digest": _digest("a"),
    "sanitized_summary_digest": _digest("b"), "sanitized_summary_saved": False,
    "label": {"intent_label": "accounting_classify", "target_box_id": "5", "quality": "good"},
    "policy_approval": {"decision": "approved", "approver_role": "manager", "reason_code": "OK"},
    "dlp_result": {"passed": True, "pii_detected": False, "secret_detected": False, "policy_violation": False},
    "retention_days": 90, "expires_at": "2026-08-27T10:00:00Z", "verified_for_training": True,
    "schema_version": "learning_event.v1",
}

_UL_BASE = {
    "log_id": "log-0001", "timestamp": "2026-05-29T09:00:01Z", "request_id": "req-0001",
    "device_id_digest": _digest("d"), "tenant_id_digest": _digest("t"), "department_id_digest": _digest("dep"),
    "request_digest": _digest("req"), "intent_label": "accounting_classify", "box_id": "5",
    "endpoint": "POST /accounting/classify", "routing_confidence": 0.92, "integration_mode": "real",
    "real_validation_done": True, "result_digest": _digest("res"), "source_digests": [_digest("s1")],
    "policy_decision": "allow", "policy_reason_code": "OK", "latency_ms": 134.5,
    "external_send_zero": True, "raw_text_logged": False, "learning_candidate": True,
    "learning_event_created": False, "retention_class": "audit_digest_only",
    "created_by_component": "connect_loop.middleware", "schema_hash": _digest("schema"),
    "schema_version": "usage_log.v1.1",
}


def _le(intent, box):
    d = copy.deepcopy(_LE_BASE)
    d["label"]["intent_label"] = intent
    d["label"]["target_box_id"] = box
    return d


def _ul(intent, box, endpoint):
    d = copy.deepcopy(_UL_BASE)
    d["intent_label"] = intent
    d["box_id"] = box
    d["endpoint"] = endpoint
    return d


# ── #1 learning_event: label.intent_label → label.target_box_id ──

@pytest.mark.parametrize("intent,box", [(i, b) for i, (b, _e) in INTENT_MAP.items()])
def test_learning_event_consistent_label_passes(intent, box):
    Draft7Validator(LEARNING_EVENT_SCHEMA).validate(_le(intent, box))


def test_learning_event_accounting_classify_to_helper1_fails():
    """결함 #1 대표 misroute: APPROVED + accounting_classify + helper1 차단."""
    with pytest.raises(ValidationError):
        Draft7Validator(LEARNING_EVENT_SCHEMA).validate(_le("accounting_classify", "helper1"))


@pytest.mark.parametrize("intent,box", [(i, b) for i, (b, _e) in INTENT_MAP.items()])
def test_learning_event_wrong_box_fails(intent, box):
    wrong = "helper1" if box != "helper1" else "5"
    with pytest.raises(ValidationError):
        Draft7Validator(LEARNING_EVENT_SCHEMA).validate(_le(intent, wrong))


def test_learning_event_status_gate_still_enforced():
    """기존 if(status==APPROVED)→decision==approved 게이트가 mapping 추가 후에도 유지."""
    bad = _le("accounting_classify", "5")
    bad["policy_approval"]["decision"] = "rejected"
    with pytest.raises(ValidationError):
        Draft7Validator(LEARNING_EVENT_SCHEMA).validate(bad)


# ── #2 usage_log: intent_label → box_id / endpoint ──

@pytest.mark.parametrize("intent,box,endpoint", [(i, b, e) for i, (b, e) in INTENT_MAP.items()])
def test_usage_log_consistent_route_passes(intent, box, endpoint):
    Draft7Validator(USAGE_LOG_SCHEMA).validate(_ul(intent, box, endpoint))


def test_usage_log_accounting_classify_to_helper1_fails():
    """결함 #2 대표 misroute: accounting_classify + helper1 + /v1/helpers/1/search 차단."""
    bad = _ul("accounting_classify", "helper1", "POST /v1/helpers/1/search")
    with pytest.raises(ValidationError):
        Draft7Validator(USAGE_LOG_SCHEMA).validate(bad)


def test_usage_log_endpoint_mismatch_fails():
    """box_id는 맞아도 endpoint가 매핑과 다르면 차단."""
    bad = _ul("general_chat", "chat", "POST /accounting/classify")
    with pytest.raises(ValidationError):
        Draft7Validator(USAGE_LOG_SCHEMA).validate(bad)
