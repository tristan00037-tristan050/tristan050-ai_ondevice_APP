"""maindev v1.2 이식 — /v1/router/decide 엔드포인트 (코덱스 구현 기준 조정).

코덱스 router_decide.py 는 schema 위반 시 fail_class='CONNECT_LOOP_SCHEMA_VALIDATION_FAILED'
(maindev 의 'CHAT_REQUEST_SCHEMA_INVALID' 와 충돌 → 코덱스 구현에 맞춰 조정).
서버측 정책은 host+text_ref 기준(클라이언트 allow 무시) — testclient host 는 localhost 로 allow.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.connect_loop.box1_router import canonical_sha256
from butler_pc_core.sidecar.routes.router_decide import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _chat_request(text: str) -> dict:
    return {
        "request_id": "req-" + uuid.uuid4().hex,
        "session_id_digest": canonical_sha256("session"),
        "tenant_id_digest": canonical_sha256("tenant"),
        "device_id": "device-local-test",
        "user_role": "employee",
        "department_id_digest": canonical_sha256("dept"),
        "text_ref": "device_local_only",
        "text_digest": canonical_sha256(text),
        "attachments": [],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "chat_request.v1",
    }


def test_router_decide_reuses_rule_based_router_for_memory_search():
    text = "지난 회의 기록 찾아줘. 문서 검색으로 확인해줘."
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": _chat_request(text), "runtime": {"runtime_text": text}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["intent_label"] == "memory_search"
    assert data["target_box_id"] == "helper1"
    assert data["target_endpoint"] == "POST /v1/helpers/1/search"
    assert data["policy_precheck"] == "allow"
    assert data["schema_version"] == "router_decision.v1"


def test_router_decide_digest_mismatch_fails_closed_to_none():
    text = "지난 회의 기록 찾아줘. 문서 검색으로 확인해줘."
    cr = _chat_request(text)
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": {"runtime_text": "다른 입력"}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["intent_label"] == "unknown"
    assert data["target_box_id"] == "none"
    assert data["target_endpoint"] == "none"
    assert data["fallback_required"] is True
    assert data["reason_code"] == "TEXT_DIGEST_MISMATCH"


def test_router_decide_rejects_raw_field_unknown_contract():
    text = "지난 회의 기록 찾아줘. 문서 검색으로 확인해줘."
    cr = _chat_request(text)
    cr["raw_text"] = text  # additionalProperties:false → 거부
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": {"runtime_text": text}},
    )
    assert response.status_code == 422
    # 코덱스 구현 기준: fail_class = CONNECT_LOOP_SCHEMA_VALIDATION_FAILED
    assert response.json()["detail"]["fail_class"] == "CONNECT_LOOP_SCHEMA_VALIDATION_FAILED"


def test_router_decide_overlong_runtime_text_sanitized_error_no_raw_echo():
    """Codex P1: runtime_text 초과 시 sanitized 422(meta-only) — 원문이 응답에 echo 되지 않는다."""
    text = "정상 본문"
    cr = _chat_request(text)
    secret = "RAWPROMPT_" + "가" * 13000  # > MAX_RUNTIME_TEXT_LENGTH
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": {"runtime_text": secret}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["fail_class"] == "CONNECT_LOOP_RUNTIME_TEXT_INVALID"
    assert "RAWPROMPT_" not in response.text  # 원문 미echo


def test_router_decide_schema_error_does_not_echo_rejected_value():
    """Codex P2: pattern/enum 위반 시 jsonschema 메시지의 rejected value(원문/secret)를 echo 하지 않는다."""
    cr = _chat_request("정상 본문")
    cr["text_digest"] = "RAWPROMPT_SECRET_NOT_A_DIGEST"  # sha256 pattern 위반
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": {"runtime_text": "정상 본문"}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["fail_class"] == "CONNECT_LOOP_SCHEMA_VALIDATION_FAILED"
    assert detail["schema_path"] == "text_digest"  # 위치(필드명)만 — 값 아님
    assert "RAWPROMPT_SECRET_NOT_A_DIGEST" not in response.text  # rejected value 미echo


def test_router_decide_runtime_as_string_sanitized_no_echo():
    """Codex P2: runtime 이 객체가 아닌 string(원문)으로 와도 sanitized 422 — 원문 미echo."""
    cr = _chat_request("정상 본문")
    secret = "RAWPROMPT_STRING_RUNTIME_LEAK"
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": secret},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["fail_class"] == "CONNECT_LOOP_RUNTIME_INVALID"
    assert "RAWPROMPT_STRING_RUNTIME_LEAK" not in response.text


def test_router_decide_chat_request_as_string_sanitized():
    """chat_request 가 객체가 아니면 sanitized 422(원문 echo 없음)."""
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": "not-an-object", "runtime": {"runtime_text": "x"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["fail_class"] == "CONNECT_LOOP_CHAT_REQUEST_INVALID"


def test_router_decide_non_local_text_ref_blocks_endpoint():
    """서버측 정책: text_ref 가 device_local_only 가 아니면 fail-closed(endpoint none)."""
    text = "지난 회의 기록 찾아줘. 문서 검색으로 확인해줘."
    cr = _chat_request(text)
    cr["text_ref"] = "device_local_only"  # 스키마상 const — 유지(서버 정책은 host 로도 판단)
    response = _client().post(
        "/v1/router/decide",
        json={"chat_request": cr, "runtime": {"runtime_text": text}},
    )
    assert response.status_code == 200, response.text
    # localhost(testclient) + device_local_only → allow 가 정상 경로임을 확인(회귀 가드)
    assert response.json()["policy_precheck"] == "allow"
