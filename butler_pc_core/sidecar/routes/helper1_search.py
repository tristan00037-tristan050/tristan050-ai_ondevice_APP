"""Thin HTTP adapter for the canonical Helper1 v2 product pipeline."""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from butler_pc_core.helper1.contracts import Helper1ContractError, require_uuid
from butler_pc_core.helper1.service import get_helper1_service

router = APIRouter()

LOCALHOST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "testclient"})
MAX_BODY_BYTES = 16 * 1024
MAX_QUERY_LENGTH = 4000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_REQUEST_FIELDS = {
    "schema_version",
    "request_id",
    "workspace_id",
    "query",
    "top_k",
    "requested_generation_id",
    "effect_intent",
}


class RequestContractError(ValueError):
    pass


@dataclass(frozen=True)
class AskEnvelope:
    request_id: str
    workspace_id: str
    query: str
    top_k: int
    requested_generation_id: str | None
    effect_intent: str


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RequestContractError("REQUEST_DUPLICATE_FIELD")
        value[key] = item
    return value


async def _json_body(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type.casefold() != "application/json":
        raise RequestContractError("REQUEST_CONTENT_TYPE_INVALID")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise RequestContractError("REQUEST_LENGTH_INVALID") from exc
        if declared < 1 or declared > MAX_BODY_BYTES:
            raise RequestContractError("REQUEST_SIZE_INVALID")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            raise RequestContractError("REQUEST_SIZE_INVALID")
    try:
        value = json.loads(
            body,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                RequestContractError("REQUEST_NUMBER_INVALID")
            ),
        )
    except RequestContractError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RequestContractError("REQUEST_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise RequestContractError("REQUEST_OBJECT_REQUIRED")
    return value


def _query_payload(value: dict[str, Any]) -> AskEnvelope:
    if set(value) != _REQUEST_FIELDS:
        raise RequestContractError("REQUEST_FIELDS_INVALID")
    if value.get("schema_version") != "butler.helper1.ask-request.v2":
        raise RequestContractError("REQUEST_SCHEMA_INVALID")
    workspace_id = value.get("workspace_id")
    request_id = value.get("request_id")
    requested_generation_id = value.get("requested_generation_id")
    try:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(request_id, "REQUEST_ID_INVALID")
        if requested_generation_id is not None:
            require_uuid(
                requested_generation_id, "REQUESTED_GENERATION_ID_INVALID"
            )
    except Helper1ContractError as exc:
        raise RequestContractError(str(exc)) from exc
    query = value.get("query")
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > MAX_QUERY_LENGTH
        or _CONTROL_RE.search(query) is not None
    ):
        raise RequestContractError("QUERY_INVALID")
    top_k = value.get("top_k")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
        raise RequestContractError("TOP_K_INVALID")
    effect_intent = value.get("effect_intent")
    if effect_intent not in {"display_only", "clipboard", "export"}:
        raise RequestContractError("EFFECT_INTENT_INVALID")
    return AskEnvelope(
        request_id=request_id,
        workspace_id=workspace_id,
        query=query.strip(),
        top_k=top_k,
        requested_generation_id=requested_generation_id,
        effect_intent=effect_intent,
    )


def _localhost_only(request: Request) -> None:
    if not is_localhost_request(request):
        raise HTTPException(
            status_code=403,
            detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"},
        )


def _invalid_request() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "schema_version": "butler.helper1.error.v2",
            "kind": "FAILED",
            "reason_code": "REQUEST_INVALID",
        },
    )


def search_integration_mode() -> str:
    """Read-only compatibility probe used by legacy usage-log tests."""
    return "real" if get_helper1_service().status()["state"] == "READY" else "unavailable"


@router.get("/v1/helpers/1/status")
async def helper1_status(request: Request, workspace_id: str | None = None) -> JSONResponse:
    _localhost_only(request)
    if workspace_id is not None:
        try:
            require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        except Helper1ContractError:
            return _invalid_request()
    service = get_helper1_service()
    value = await anyio.to_thread.run_sync(service.status, workspace_id)
    return JSONResponse(status_code=200, content=value)


@router.post("/v1/helpers/1/search")
async def helper1_search(request: Request) -> JSONResponse:
    _localhost_only(request)
    try:
        envelope = _query_payload(await _json_body(request))
    except RequestContractError:
        return _invalid_request()
    service = get_helper1_service()
    status, value = await anyio.to_thread.run_sync(
        functools.partial(service.search, **vars(envelope))
    )
    return JSONResponse(status_code=status, content=value)


@router.post("/v1/helpers/1/ask")
async def helper1_ask(request: Request) -> JSONResponse:
    _localhost_only(request)
    try:
        envelope = _query_payload(await _json_body(request))
    except RequestContractError:
        return _invalid_request()
    service = get_helper1_service()
    result = await anyio.to_thread.run_sync(
        functools.partial(service.ask, **vars(envelope))
    )
    return JSONResponse(status_code=result.http_status, content=result.to_public_dict())
