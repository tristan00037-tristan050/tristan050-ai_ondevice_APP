"""Codex P1 #2 정정 회귀 방지 (2026-05-27).

router_decision.schema.json: intent_label/target_box_id/target_endpoint가
독립 enum이라 misroute(예: accounting_classify + helper1)가 통과하던 결함을
if/then/allOf로 차단. intent_label description의 실측 매핑표를 fail-closed
SSOT로 강제하는지 검증한다.

(결함 #1 learning_event approved-only는 기존 test_schema_contract.py의
 test_learning_event_approved_requires_policy_approved 가 이미 가드하므로 중복 추가하지 않음.)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_SCHEMA = json.loads(
    (REPO_ROOT / "schemas/connect_loop/router_decision.schema.json").read_text(encoding="utf-8")
)

# intent_label description(L27)의 실측 매핑표.
INTENT_MAPPING = {
    "memory_search": ("helper1", "POST /v1/helpers/1/search"),
    "form_convert": ("2", "POST /v1/cards/2/rewrite"),
    "draft_write": ("3", "POST /v1/cards/3/draft"),
    "accounting_classify": ("5", "POST /accounting/classify"),
    "general_chat": ("chat", "POST /v1/chat/completions"),
    "unknown": ("none", "none"),
}


def _decision(intent, box_id, endpoint, fallback=False):
    return {
        "request_id": "req-0001",
        "intent_label": intent,
        "target_box_id": box_id,
        "target_endpoint": endpoint,
        "routing_confidence": 0.9,
        "reason_code": "INTENT_KEYWORD_MATCH",
        "fallback_required": fallback,
        "policy_precheck": "allow",
        "schema_version": "router_decision.v1",
    }


@pytest.mark.parametrize("intent,box_id,endpoint", [(i, b, e) for i, (b, e) in INTENT_MAPPING.items()])
def test_correct_intent_mapping_passes(intent, box_id, endpoint):
    """매핑표대로의 조합은 통과 (over-constrain 회귀 방지)."""
    fallback = intent == "unknown"
    Draft7Validator(ROUTER_SCHEMA).validate(_decision(intent, box_id, endpoint, fallback))


def test_accounting_classify_to_helper1_fails():
    """결함 #2 대표 misroute: accounting_classify + helper1 차단."""
    bad = _decision("accounting_classify", "helper1", "POST /v1/helpers/1/search")
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


def test_accounting_classify_to_endpoint_none_fails():
    """Codex 명시 사례: accounting_classify + target_endpoint=none 차단."""
    bad = _decision("accounting_classify", "5", "none")
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


@pytest.mark.parametrize("intent,box_id,endpoint", [(i, b, e) for i, (b, e) in INTENT_MAPPING.items() if i != "unknown"])
def test_each_known_intent_wrong_endpoint_fails(intent, box_id, endpoint):
    """각 known intent에 다른 intent의 endpoint를 붙이면 차단 (전 intent enforce)."""
    wrong_endpoint = "POST /v1/cards/3/draft" if endpoint != "POST /v1/cards/3/draft" else "POST /accounting/classify"
    bad = _decision(intent, box_id, wrong_endpoint)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


def test_unknown_must_route_to_none_with_fallback():
    """unknown → none/none + fallback_required=true 강제."""
    Draft7Validator(ROUTER_SCHEMA).validate(_decision("unknown", "none", "none", fallback=True))

    bad_route = _decision("unknown", "helper1", "POST /v1/helpers/1/search", fallback=False)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad_route)


def test_unknown_with_fallback_false_fails():
    """unknown인데 fallback_required=false면 차단."""
    bad = _decision("unknown", "none", "none", fallback=False)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)
