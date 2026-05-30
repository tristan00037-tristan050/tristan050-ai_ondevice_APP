from __future__ import annotations

import hashlib

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from butler_pc_core.connect_loop.box1_router import (
    RouterRuntimeContext,
    RuleBasedBox1Router,
)
from butler_pc_core.connect_loop.schema_validator import load_schema


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _chat_request() -> dict:
    return {
        "request_id": "req-box1-router-001",
        "session_id_digest": _digest("session"),
        "tenant_id_digest": _digest("tenant"),
        "device_id": "device-local-001",
        "user_role": "employee",
        "department_id_digest": _digest("department"),
        "text_ref": "device_local_only",
        "text_digest": _digest("message"),
        "attachments": [],
        "created_at": "2026-05-30T10:00:00+09:00",
        "schema_version": "chat_request.v1",
    }


def _decide(text: str | None, policy: str = "allow") -> dict:
    router = RuleBasedBox1Router()
    return router.decide(_chat_request(), RouterRuntimeContext(runtime_text=text, policy_precheck=policy))


def test_memory_search_routes_to_helper1_search():
    decision = _decide("지난 계약서와 이전 회의록을 찾아줘")
    assert decision["intent_label"] == "memory_search"
    assert decision["target_box_id"] == "helper1"
    assert decision["target_endpoint"] == "POST /v1/helpers/1/search"
    assert decision["fallback_required"] is False


def test_form_convert_routes_to_box2_rewrite():
    decision = _decide("외부 문서를 우리 양식으로 변환하고 서식 맞춰줘")
    assert decision["intent_label"] == "form_convert"
    assert decision["target_box_id"] == "2"
    assert decision["target_endpoint"] == "POST /v1/cards/2/rewrite"


def test_draft_write_routes_to_box3_draft():
    decision = _decide("새 상황에 맞는 초안 작성과 보고서 작성 부탁해")
    assert decision["intent_label"] == "draft_write"
    assert decision["target_box_id"] == "3"
    assert decision["target_endpoint"] == "POST /v1/cards/3/draft"


def test_accounting_classify_routes_to_box5_accounting():
    decision = _decide("거래내역 계정과목 회계분류와 분개를 해줘")
    assert decision["intent_label"] == "accounting_classify"
    assert decision["target_box_id"] == "5"
    assert decision["target_endpoint"] == "POST /accounting/classify"


def test_general_chat_has_no_endpoint_and_fallback():
    decision = _decide("안녕하세요 무엇을 할 수 있나요 기능 설명 부탁해")
    assert decision["intent_label"] == "general_chat"
    assert decision["target_box_id"] == "chat"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


def test_unknown_has_no_endpoint_and_fallback():
    decision = _decide(None)
    assert decision["intent_label"] == "unknown"
    assert decision["target_box_id"] == "none"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


def test_low_confidence_becomes_unknown():
    decision = _decide("검토")
    assert decision["intent_label"] == "unknown"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


def test_ambiguous_input_becomes_unknown():
    decision = _decide("이전 자료를 찾아 새 초안 작성도 해줘")
    assert decision["intent_label"] == "unknown"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


@pytest.mark.parametrize("policy", ["block", "needs_review"])
def test_policy_block_forces_endpoint_none(policy):
    decision = _decide("거래내역 계정과목 회계분류와 분개를 해줘", policy)
    assert decision["intent_label"] == "accounting_classify"
    assert decision["target_box_id"] == "5"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True
    assert decision["policy_precheck"] == policy


def test_policy_needs_review_forces_endpoint_none():
    decision = _decide("외부 문서를 우리 양식으로 변환하고 서식 맞춰줘", "needs_review")
    assert decision["intent_label"] == "form_convert"
    assert decision["target_box_id"] == "2"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True


def test_decision_self_validates_against_schema():
    decision = _decide("거래내역 계정과목 회계분류와 분개를 해줘")
    Draft7Validator(load_schema("router_decision.schema.json")).validate(decision)


def test_misroute_fixture_fails_schema_validation():
    decision = _decide("거래내역 계정과목 회계분류와 분개를 해줘")
    decision["target_box_id"] = "helper1"
    decision["target_endpoint"] = "POST /v1/helpers/1/search"
    with pytest.raises(ValidationError):
        Draft7Validator(load_schema("router_decision.schema.json")).validate(decision)
