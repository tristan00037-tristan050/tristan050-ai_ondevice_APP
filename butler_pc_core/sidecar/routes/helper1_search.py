"""Helper 1 (memory) search/ask sidecar router.

Contract-safe by default. Real retrieval runs only when the local SDK and all
runtime assets are present. No raw query, answer, or chunk text is persisted to
audit; only sha256 digests are recorded. No network calls are made here.
"""
from __future__ import annotations

import hashlib
import os
import time

import anyio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_QUERY_LENGTH = 4000

DEFAULT_SDK_PATH = str(
    Path.home() / "Desktop/도우미폴더/넘겨줄도우미모델/도우미1_기억/sdk"
)

_RUNTIME_ASSETS = [
    Path("/private/tmp/bge_m3_combined"),
    Path("/Volumes/T7 Shield/학습모델/butler-1.7b-v4-rt/butler-1.7b-v4-rt-q4_k_m.gguf"),
    Path.home() / "Desktop/기억도우미/runtime/private/helper1_chunks_v2.local.jsonl",
    Path.home() / "Desktop/기억도우미/runtime/private/helper1_embeddings_v2.npy",
    Path.home() / "Desktop/기억도우미/runtime/private/helper1_bm25_v2.pkl",
]

CONTRACT_ONLY_ANSWER = "contract_only_response"


class Helper1Query(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)
    top_k: int = Field(default=5, ge=1, le=50)


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def _sdk_path() -> str:
    return os.environ.get("HELPER1_SDK_PATH", DEFAULT_SDK_PATH)


def _assets_present() -> bool:
    return all(p.exists() for p in _RUNTIME_ASSETS)


def _sdk_present() -> bool:
    return (Path(_sdk_path()) / "memory_helper.py").is_file()


def integration_mode() -> str:
    # Codex P2 #1 (2026-05-27): SDK 부재(memory_helper.py 없음)에 "blocked"를
    # 반환하면 핸들러가 `if mode == "real"` 분기만 가져 fall through → HTTP 200 +
    # empty/stub을 반환했고, "blocked"는 endpoint contract(real/contract_only)
    # 밖이었다. SDK 부재를 honest fail-safe인 contract_only로 매핑해 응답이
    # real_validation_done=false로 명시되게 한다(stub을 real처럼 위장하지 않음).
    if not _sdk_present() or not _assets_present():
        return "contract_only"
    return "real"


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_memory_helper():
    import sys

    sdk_path = _sdk_path()
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)
    import memory_helper  # type: ignore

    return memory_helper


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

    mode = integration_mode()
    start = time.time()
    results: list[dict[str, Any]] = []
    real_validation_done = False
    sdk_import_failure: dict[str, str] | None = None

    if mode == "real":
        try:
            mh = _load_memory_helper()
        except ImportError as exc:
            # Codex P2 #2 (2026-05-27): SDK 파일은 있으나 로컬 의존성 결손으로
            # import가 raise하면 HTTP 500으로 endpoint가 unusable이던 것을, 약속된
            # contract-only로 자동 downgrade. raw 메시지 노출 0 — error_class +
            # repr 기반 16자 digest만 (PR #755 no-raw-output 정합).
            mode = "contract_only"
            sdk_import_failure = {
                "error_class": exc.__class__.__name__,
                "error_digest": hashlib.sha256(repr(exc).encode("utf-8")).hexdigest()[:16],
            }
        else:
            raw_results = await anyio.to_thread.run_sync(mh.find, payload.query, payload.top_k)
            for item in raw_results:
                results.append({
                    "chunk_id": item.get("chunk_id") or item.get("id"),
                    "score": item.get("score"),
                    "source_digest": _source_digest_for(item),
                })
            real_validation_done = True

    response: dict[str, Any] = {
        "integration_mode": mode,
        "real_validation_done": real_validation_done,
        "results": results,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "external_send_zero": True,
        "raw_text_logged": False,
        "audit": _audit(payload.query),
    }
    if sdk_import_failure is not None:
        response["sdk_import_failure"] = sdk_import_failure
    return response


@router.post("/v1/helpers/1/ask")
async def helper1_ask(payload: Helper1Query, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    mode = integration_mode()
    start = time.time()
    answer = CONTRACT_ONLY_ANSWER
    sources: list[dict[str, Any]] = []
    real_validation_done = False
    sdk_import_failure: dict[str, str] | None = None

    if mode == "real":
        try:
            mh = _load_memory_helper()
        except ImportError as exc:
            # Codex P2 #2 (2026-05-27): SDK import 실패를 HTTP 500 대신 contract-only로
            # 자동 downgrade. raw 메시지 노출 0 — error_class + repr 기반 16자 digest만.
            mode = "contract_only"
            answer = CONTRACT_ONLY_ANSWER
            sdk_import_failure = {
                "error_class": exc.__class__.__name__,
                "error_digest": hashlib.sha256(repr(exc).encode("utf-8")).hexdigest()[:16],
            }
        else:
            produced = await anyio.to_thread.run_sync(mh.ask, payload.query)
            answer = produced.get("answer", "")
            for item in produced.get("sources", []) or []:
                sources.append({
                    "chunk_id": item.get("chunk_id") or item.get("id"),
                    "score": item.get("score"),
                    "source_digest": _source_digest_for(item),
                })
            real_validation_done = True

    response: dict[str, Any] = {
        "integration_mode": mode,
        "real_validation_done": real_validation_done,
        "answer": answer,
        "sources": sources,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "external_send_zero": True,
        "raw_text_logged": False,
        "audit": _audit(payload.query),
    }
    if sdk_import_failure is not None:
        response["sdk_import_failure"] = sdk_import_failure
    return response
