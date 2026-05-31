"""Connect Loop router decision HTTP route.

This module is the PR-D follow-up bridge from the desktop chat UI to the
already-sealed Box 1 router. It intentionally owns only HTTP/auth-adjacent
translation and server-side local policy; routing rules remain in
``RuleBasedBox1Router``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from jsonschema.exceptions import ValidationError
from pydantic import BaseModel

from butler_pc_core.connect_loop.box1_router import (
    RouterRuntimeContext,
    RuleBasedBox1Router,
)
from butler_pc_core.connect_loop.schema_validator import (
    validate_chat_request,
    validate_router_decision,
)

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_RUNTIME_TEXT_LENGTH = 12_000


class RouterDecidePayload(BaseModel):
    # Codex P1+P2: chat_request/runtime 을 Any 로 받아 타입/내용 검증을 라우트 내부에서 수행한다.
    # Pydantic 필드 타입 제약(dict/str/max_length)의 기본 422 응답은 rejected input(=원문 runtime_text
    # 가 string/list 로 온 경우 포함)을 echo 하므로, raw-output/meta-only 불변식 위반을 막기 위해
    # 모델 단 타입 제약을 두지 않고 모두 sanitized 오류로 처리한다.
    chat_request: Any = None
    runtime: Any = None


def _server_side_policy_precheck(
    chat_request: dict[str, Any],
    request: Request,
) -> tuple[str, str]:
    """Return a fail-closed server-side local policy result.

    Client-provided "allow" values are deliberately ignored. The sidecar
    decides from the actual request host plus the immutable chat_request text
    reference.
    """
    host = request.client.host if request.client else ""
    if host not in LOCALHOST_HOSTS:
        return "block", "LOCALHOST_ONLY"
    if chat_request.get("text_ref") != "device_local_only":
        return "block", "TEXT_REF_NOT_LOCAL_ONLY"
    return "allow", "LOCAL_ONLY_ALLOWED"


def _raise_schema_error(exc: ValidationError) -> None:
    # Codex P2: jsonschema exc.message 는 pattern/enum 실패 시 rejected value(원문/secret 가능)를
    # 포함한다. no-raw-output 불변식을 위해 message 는 정적 문자열로, 위치는 schema_path(필드 경로,
    # 값 아님)만 노출한다. (validator_path 는 실패한 검증 키워드로 값이 아님.)
    path = ".".join(str(item) for item in exc.path) or "<root>"
    validator = str(getattr(exc, "validator", "") or "")
    raise HTTPException(
        status_code=422,
        detail={
            "fail_class": "CONNECT_LOOP_SCHEMA_VALIDATION_FAILED",
            "schema_path": path,
            "validator": validator,
            "message": "chat_request failed contract validation",
        },
    ) from exc


@router.post("/v1/router/decide")
async def decide_router(payload: RouterDecidePayload, request: Request) -> dict[str, Any]:
    # Codex P2: chat_request/runtime 의 타입 자체를 sanitized 오류로 검증(rejected input echo 차단).
    if not isinstance(payload.chat_request, dict):
        raise HTTPException(
            status_code=422,
            detail={"fail_class": "CONNECT_LOOP_CHAT_REQUEST_INVALID", "message": "chat_request must be an object"},
        )
    if not isinstance(payload.runtime, dict):
        raise HTTPException(
            status_code=422,
            detail={"fail_class": "CONNECT_LOOP_RUNTIME_INVALID", "message": "runtime must be an object"},
        )

    chat_request = dict(payload.chat_request)
    try:
        validate_chat_request(chat_request)
    except ValidationError as exc:
        _raise_schema_error(exc)

    # Codex P1: runtime_text 길이/타입 검증을 sanitized(meta-only) 오류로 처리 — 원문 미echo.
    runtime_text = payload.runtime.get("runtime_text", "")
    if not isinstance(runtime_text, str) or len(runtime_text) > MAX_RUNTIME_TEXT_LENGTH:
        raise HTTPException(
            status_code=422,
            detail={
                "fail_class": "CONNECT_LOOP_RUNTIME_TEXT_INVALID",
                "message": "runtime_text must be a string within the allowed length",
            },
        )

    policy_precheck, reason_code = _server_side_policy_precheck(chat_request, request)
    decision = RuleBasedBox1Router().decide(
        chat_request,
        RouterRuntimeContext(
            runtime_text=runtime_text,
            policy_precheck=policy_precheck,  # type: ignore[arg-type]
            policy_reason_code=reason_code,
        ),
    )
    try:
        validate_router_decision(decision)
    except ValidationError as exc:
        _raise_schema_error(exc)
    return decision
