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
from pydantic import BaseModel, Field

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
    # Codex P1: runtime 을 dict 로 받아 runtime_text 길이/타입 검증을 라우트 내부에서 수행한다.
    # Pydantic 필드 제약(max_length 등)의 기본 422 응답은 offending input(=원문 runtime_text)을
    # 그대로 echo 하므로, raw-output/meta-only 불변식 위반을 막기 위해 모델 단 제약을 두지 않는다.
    chat_request: dict[str, Any]
    runtime: dict[str, Any] = Field(default_factory=dict)


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
    path = ".".join(str(item) for item in exc.path) or "<root>"
    raise HTTPException(
        status_code=422,
        detail={
            "fail_class": "CONNECT_LOOP_SCHEMA_VALIDATION_FAILED",
            "schema_path": path,
            "message": exc.message,
        },
    ) from exc


@router.post("/v1/router/decide")
async def decide_router(payload: RouterDecidePayload, request: Request) -> dict[str, Any]:
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
