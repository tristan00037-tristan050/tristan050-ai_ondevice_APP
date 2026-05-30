from __future__ import annotations

import copy
import hashlib

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from butler_pc_core.connect_loop.box1_router import RouterRuntimeContext, RuleBasedBox1Router
from butler_pc_core.connect_loop.schema_validator import router_decision_schema


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


BASE_CHAT_REQUEST = {
    "request_id": "req-prc-0001",
    "session_id_digest": _digest("session"),
    "tenant_id_digest": _digest("tenant"),
    "device_id": "device-local-001",
    "user_role": "employee",
    "department_id_digest": _digest("department"),
    "text_ref": "device_local_only",
    "text_digest": _digest(""),
    "attachments": [],
    "created_at": "2026-05-30T09:00:00Z",
    "schema_version": "chat_request.v1",
}


def _request_for_text(text: str | None) -> dict:
    request = copy.deepcopy(BASE_CHAT_REQUEST)
    request["text_digest"] = _digest(text or "")
    return request


def _decide(text: str | None, policy: str = "allow", *, request_text: str | None = None) -> dict:
    return RuleBasedBox1Router().decide(
        _request_for_text(text if request_text is None else request_text),
        RouterRuntimeContext(runtime_text=text, policy_precheck=policy),
    )


def _assert_route(decision: dict, intent: str, box_id: str, endpoint: str, fallback: bool) -> None:
    assert decision["intent_label"] == intent
    assert decision["target_box_id"] == box_id
    assert decision["target_endpoint"] == endpoint
    assert decision["fallback_required"] is fallback
    Draft7Validator(router_decision_schema()).validate(decision)


def test_memory_search_routes_to_helper1_search():
    d = _decide("이전 과거 문서 자료를 찾아줘 검색")
    _assert_route(d, "memory_search", "helper1", "POST /v1/helpers/1/search", False)


def test_form_convert_routes_to_box2_rewrite():
    d = _decide("외부 양식을 우리 양식으로 변환하고 서식 맞춰")
    _assert_route(d, "form_convert", "2", "POST /v1/cards/2/rewrite", False)


def test_draft_write_routes_to_box3_draft():
    d = _decide("보고서 초안 작성하고 메일 문안 써줘")
    _assert_route(d, "draft_write", "3", "POST /v1/cards/3/draft", False)


def test_accounting_classify_routes_to_box5_accounting():
    d = _decide("은행거래 거래내역 계정과목 회계분류 분개")
    _assert_route(d, "accounting_classify", "5", "POST /accounting/classify", False)


def test_general_chat_has_no_endpoint_and_fallback():
    d = _decide("안녕 기능 설명 도움말 사용법 알려줘")
    _assert_route(d, "general_chat", "chat", "none", True)


def test_unknown_has_no_endpoint_and_fallback():
    d = _decide("오늘 점심 메뉴")
    _assert_route(d, "unknown", "none", "none", True)


def test_low_confidence_becomes_unknown():
    d = _decide("자료")
    _assert_route(d, "unknown", "none", "none", True)
    assert d["reason_code"] == "LOW_CONFIDENCE_FALLBACK"


def test_ambiguous_input_becomes_unknown():
    d = _decide("이전 문서 찾아줘 우리 양식으로")
    _assert_route(d, "unknown", "none", "none", True)
    assert d["reason_code"] == "AMBIGUOUS_INTENT_FALLBACK"


def test_policy_block_forces_endpoint_none():
    d = _decide("은행거래 거래내역 계정과목 회계분류 분개", policy="block")
    _assert_route(d, "accounting_classify", "5", "none", True)
    assert d["policy_precheck"] == "block"


def test_policy_needs_review_forces_endpoint_none():
    d = _decide("외부 양식을 우리 양식으로 변환하고 서식 맞춰", policy="needs_review")
    _assert_route(d, "form_convert", "2", "none", True)
    assert d["policy_precheck"] == "needs_review"


def test_runtime_text_missing_becomes_unknown():
    d = _decide(None)
    _assert_route(d, "unknown", "none", "none", True)
    assert d["routing_confidence"] == 0.0


def test_runtime_text_digest_mismatch_falls_back_to_unknown():
    d = _decide("은행거래 거래내역 계정과목 회계분류 분개", request_text="다른 원문")
    _assert_route(d, "unknown", "none", "none", True)
    assert d["routing_confidence"] == 0.0
    assert d["reason_code"] == "TEXT_DIGEST_MISMATCH_FALLBACK"


def test_runtime_text_digest_mismatch_never_exposes_callable_endpoint():
    d = _decide("이전 과거 문서 자료를 찾아줘 검색", request_text="다른 원문")
    assert d["target_endpoint"] == "none"
    assert d["fallback_required"] is True


def test_decision_self_validates_against_schema():
    d = _decide("이전 과거 문서 자료를 찾아줘 검색")
    Draft7Validator(router_decision_schema()).validate(d)


def test_misroute_fixture_fails_schema_validation():
    bad = _decide("은행거래 거래내역 계정과목 회계분류 분개")
    bad["target_box_id"] = "helper1"
    bad["target_endpoint"] = "POST /v1/helpers/1/search"
    with pytest.raises(ValidationError):
        Draft7Validator(router_decision_schema()).validate(bad)


def test_invalid_policy_value_rejected_before_decision():
    with pytest.raises(ValueError):
        _decide("이전 과거 문서 자료를 찾아줘 검색", policy="deny")
