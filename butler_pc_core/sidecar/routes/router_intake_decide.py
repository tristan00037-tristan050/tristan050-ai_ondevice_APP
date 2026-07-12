"""HTTP bridge for Box1 attachment-aware intake decision v3.6.

Production invariants:
- route-local capability token verification; no static test-token fallback;
- localhost + device_local_only preserved;
- no box/helper/company endpoint calls;
- sanitized errors only, no rejected raw input echo.
"""
from __future__ import annotations

import json
from typing import Any, Optional

try:  # FastAPI is a runtime dependency of the sidecar; tests may monkeypatch.
    from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
except Exception:  # pragma: no cover - import failure is handled at app import time in real sidecar
    APIRouter = None  # type: ignore
    File = Form = Header = UploadFile = None  # type: ignore
    HTTPException = RuntimeError  # type: ignore
    Request = Any  # type: ignore

from butler_pc_core.connect_loop.attachment_features import RuntimeAttachment, extract_attachment_features
from butler_pc_core.connect_loop.intake_router import IntakeContractError, decide_intake
from butler_pc_core.model_tier.shadow_observer import (
    complete_box1_shadow_best_effort,
    prepare_box1_shadow_best_effort,
    response_digest_best_effort,
)

try:
    from butler_pc_core.auth.capability_token import CapabilityTokenError, CapabilityTokenManager, auth_error_payload
except Exception:  # production fallback is not allowed; route will fail-closed.
    CapabilityTokenError = None  # type: ignore
    CapabilityTokenManager = None  # type: ignore
    auth_error_payload = None  # type: ignore

try:
    from butler_pc_core.connect_loop.schema_validator import validate_chat_request
except Exception:
    validate_chat_request = None  # type: ignore

router = APIRouter() if APIRouter is not None else None
_TOKEN_MANAGER = CapabilityTokenManager() if CapabilityTokenManager is not None else None
LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_RUNTIME_TEXT_LENGTH = 12_000
MAX_FILE_COUNT = 12
MAX_FILE_BYTES = 25 * 1024 * 1024


def _raise(status_code: int, fail_class: str, message: str = "request rejected") -> None:
    raise HTTPException(status_code=status_code, detail={"fail_class": fail_class, "message": message})


def _verify_capability_token(authorization: str | None) -> None:
    if _TOKEN_MANAGER is None or CapabilityTokenError is None or auth_error_payload is None:
        _raise(503, "CAPABILITY_TOKEN_VERIFIER_UNAVAILABLE", "capability verifier unavailable")
    try:
        _TOKEN_MANAGER.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:  # type: ignore[misc]
        fail = getattr(exc, "fail_class", None)
        value = getattr(fail, "value", str(fail))
        status = 401 if value == "CAPABILITY_TOKEN_MISSING" else 403
        payload = auth_error_payload(exc)  # type: ignore[operator]
        # Payload intentionally contains only fail class and static message from auth module.
        raise HTTPException(status_code=status, detail=payload) from exc


def _validate_local_request(chat_request: dict[str, Any], request: Request) -> None:
    host = request.client.host if getattr(request, "client", None) else ""
    if host not in LOCALHOST_HOSTS:
        _raise(403, "LOCALHOST_ONLY", "localhost only")
    if chat_request.get("text_ref") != "device_local_only":
        _raise(403, "TEXT_REF_NOT_LOCAL_ONLY", "text_ref must be device local only")


def _parse_chat_request(chat_request_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(chat_request_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"fail_class": "CHAT_REQUEST_JSON_INVALID"}) from exc
    if not isinstance(payload, dict):
        _raise(422, "CHAT_REQUEST_JSON_INVALID", "chat_request_json must be object")
    if validate_chat_request is not None:
        try:
            validate_chat_request(payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"fail_class": "CHAT_REQUEST_SCHEMA_INVALID"}) from exc
    return payload


async def _read_runtime_attachments(files: list[UploadFile] | None) -> list[RuntimeAttachment]:  # type: ignore[valid-type]
    files = files or []
    if len(files) > MAX_FILE_COUNT:
        _raise(413, "INTAKE_TOO_MANY_FILES", "too many attachments")
    attachments: list[RuntimeAttachment] = []
    for file in files:
        raw = await file.read()
        if len(raw) > MAX_FILE_BYTES:
            _raise(413, "INTAKE_FILE_TOO_LARGE", "attachment too large")
        attachments.append(RuntimeAttachment(data=raw, filename=getattr(file, "filename", None), content_type=getattr(file, "content_type", None)))
    return attachments


if router is not None:
    @router.post("/v1/router/intake-decide")
    async def decide_intake_route(
        request: Request,
        chat_request_json: str = Form(...),
        runtime_text: str = Form(""),
        authorization: Optional[str] = Header(default=None),
        files: list[UploadFile] = File(default=[]),  # type: ignore[valid-type]
    ) -> dict[str, Any]:
        _verify_capability_token(authorization)
        if not isinstance(runtime_text, str) or len(runtime_text) > MAX_RUNTIME_TEXT_LENGTH:
            _raise(422, "CONNECT_LOOP_RUNTIME_TEXT_INVALID", "runtime_text invalid")
        chat_request = _parse_chat_request(chat_request_json)
        _validate_local_request(chat_request, request)
        attachments = await _read_runtime_attachments(files)
        bundle = extract_attachment_features(attachments)
        request_digest = str(chat_request.get("text_digest", ""))
        try:
            shadow_pre_context = prepare_box1_shadow_best_effort(
                request_digest=request_digest,
                facts={
                "payload_digest": request_digest,
                "input_chars": len(runtime_text),
                "attachment_count": len(attachments),
                "total_attachment_bytes": sum(len(item.data) for item in attachments),
                "requested_output_tokens": 0,
                "reference_count": len(attachments),
                "structured_output_required": bool(attachments),
                "deterministic_path_available": False,
                "ambiguity_score": 0.5,
                },
            )
        except Exception:
            shadow_pre_context = None
        try:
            decision = decide_intake(
                request_id=str(chat_request.get("request_id", "")),
                attachment_bundle=bundle,
                runtime_text=runtime_text,
                policy_ready_override=None,
            )
        except IntakeContractError as exc:
            _raise(422, exc.fail_class, "intake contract rejected")
        try:
            complete_box1_shadow_best_effort(
                pre_context=shadow_pre_context,
                actual_response_digest=response_digest_best_effort(decision),
            )
        except Exception:
            pass
        return decision
