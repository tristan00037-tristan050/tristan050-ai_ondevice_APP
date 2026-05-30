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
    "general_chat": ("chat", "none"),
    "unknown": ("none", "none"),
}
# chat은 sidecar 미등록 → general_chat도 unknown처럼 fallback_required=true.
_FALLBACK_INTENTS = {"unknown", "general_chat"}


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
    fallback = intent in _FALLBACK_INTENTS
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


# ── Codex P1 (2026-05-30): 정책 우선 — non-allow precheck는 callable route 불가 ──

def _with_precheck(intent, box_id, endpoint, precheck, fallback=False):
    d = _decision(intent, box_id, endpoint, fallback)
    d["policy_precheck"] = precheck
    return d


@pytest.mark.parametrize("precheck", ["block", "needs_review"])
def test_non_allow_precheck_with_real_endpoint_fails(precheck):
    """blocked/검토대기 precheck 가 실제 endpoint(호출 가능 route)로 표현되면 차단."""
    bad = _with_precheck("accounting_classify", "5", "POST /accounting/classify", precheck, fallback=False)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


@pytest.mark.parametrize("precheck", ["block", "needs_review"])
def test_non_allow_precheck_requires_fallback_true(precheck):
    """non-allow precheck 는 fallback_required=true 강제(false면 차단)."""
    bad = _with_precheck("accounting_classify", "5", "none", precheck, fallback=False)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


@pytest.mark.parametrize("precheck", ["block", "needs_review"])
def test_non_allow_precheck_to_none_with_fallback_passes(precheck):
    """non-allow precheck + endpoint=none + fallback_required=true 는 통과(정당한 blocked 결정)."""
    ok = _with_precheck("accounting_classify", "5", "none", precheck, fallback=True)
    Draft7Validator(ROUTER_SCHEMA).validate(ok)


def test_allow_precheck_real_endpoint_still_passes():
    """precheck=allow + 정합 endpoint 는 그대로 통과(over-constrain 회귀 방지)."""
    Draft7Validator(ROUTER_SCHEMA).validate(
        _decision("accounting_classify", "5", "POST /accounting/classify", fallback=False)
    )


@pytest.mark.parametrize("precheck", ["block", "needs_review"])
def test_non_allow_precheck_still_enforces_box_mapping(precheck):
    """Codex P2 (2026-05-30): blocked/검토대기 결정에서도 intent→target_box_id const 는 유지.
    endpoint 만 allow-gate, box 매핑은 정책과 무관하게 항상 강제 → box mislabel 차단."""
    bad = _with_precheck("accounting_classify", "helper1", "none", precheck, fallback=True)
    with pytest.raises(ValidationError):
        Draft7Validator(ROUTER_SCHEMA).validate(bad)


@pytest.mark.parametrize("precheck", ["block", "needs_review"])
def test_non_allow_precheck_correct_box_none_endpoint_passes(precheck):
    """blocked 결정 + 정합 box + endpoint=none + fallback=true 는 통과."""
    Draft7Validator(ROUTER_SCHEMA).validate(
        _with_precheck("accounting_classify", "5", "none", precheck, fallback=True)
    )
