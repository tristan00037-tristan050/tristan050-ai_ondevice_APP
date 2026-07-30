"""Helper 1 (memory) search/ask sidecar router.

Contract-safe by default. Real retrieval runs only when the local SDK and all
runtime assets are present. No raw query, answer, or chunk text is persisted to
audit; only sha256 digests are recorded. No network calls are made here.
"""
from __future__ import annotations

import hashlib
import time

import anyio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from butler_pc_core.assets import get_asset_service
from butler_pc_core.assets.errors import AssetError

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_QUERY_LENGTH = 4000

class Helper1Query(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)
    top_k: int = Field(default=5, ge=1, le=50)


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def search_integration_mode() -> str:
    return _integration_mode("helper1.search")


def ask_integration_mode() -> str:
    return _integration_mode("helper1.ask")


def _integration_mode(capability: str) -> str:
    group = capability
    try:
        snapshot = get_asset_service().get_cached_status()
    except AssetError:
        return "unavailable"
    for item in snapshot.get("groups", []):
        if (
            isinstance(item, dict)
            and item.get("asset_group") == group
            and item.get("state") == "AVAILABLE"
        ):
            return "real"
    return "unavailable"


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_memory_helper():
    from butler_pc_core.helper1 import memory_helper
    return memory_helper


def _asset_unavailable(capability: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "ok": False,
            "code": "ASSET_UNAVAILABLE",
            "capability": capability,
            "retryable": False,
        },
    )


def _source_digest_for(item: dict[str, Any]) -> str:
    basis = str(item.get("chunk_id") or item.get("id") or item.get("text") or item)
    return "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _audit(query: str) -> dict[str, Any]:
    return {
        "query_digest": _digest(query),
        "policy_decision": "allow_local_only",
        "reason": "helper1_memory_search",
    }


@router.post("/v1/helpers/1/search")
async def helper1_search(payload: Helper1Query, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    mode = search_integration_mode()
    if mode != "real":
        raise _asset_unavailable("helper1.search")
    start = time.time()
    results: list[dict[str, Any]] = []
    try:
        mh = _load_memory_helper()
        raw_results = await anyio.to_thread.run_sync(
            mh.find, payload.query, payload.top_k
        )
    except (AssetError, ImportError):
        raise _asset_unavailable("helper1.search")
    for item in raw_results:
        results.append({
            "chunk_id": item.get("chunk_id") or item.get("id"),
            "score": item.get("score"),
            "source_digest": _source_digest_for(item),
        })

    response: dict[str, Any] = {
        "integration_mode": mode,
        "real_validation_done": True,
        "results": results,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "external_send_zero": True,
        "raw_text_logged": False,
        "audit": _audit(payload.query),
    }
    return response


@router.post("/v1/helpers/1/ask")
async def helper1_ask(payload: Helper1Query, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    mode = ask_integration_mode()
    if mode != "real":
        raise _asset_unavailable("helper1.ask")
    start = time.time()
    answer = ""
    sources: list[dict[str, Any]] = []
    try:
        mh = _load_memory_helper()
        produced = await anyio.to_thread.run_sync(mh.ask, payload.query)
    except (AssetError, ImportError):
        raise _asset_unavailable("helper1.ask")
    answer = produced.get("answer", "")
    for item in produced.get("sources", []) or []:
        sources.append({
            "chunk_id": item.get("chunk_id") or item.get("id"),
            "score": item.get("score"),
            "source_digest": _source_digest_for(item),
        })

    response: dict[str, Any] = {
        "integration_mode": mode,
        "real_validation_done": True,
        "answer": answer,
        "sources": sources,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "external_send_zero": True,
        "raw_text_logged": False,
        "audit": _audit(payload.query),
    }
    return response
