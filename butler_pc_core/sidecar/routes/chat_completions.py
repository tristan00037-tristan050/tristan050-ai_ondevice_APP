from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from butler_pc_core.model_registry.ip3_model_registry import BUTLER_1_7B_V4_RT

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
BLOCK_MESSAGE = "현재 sample replay 모드입니다. live 진입 시 IP1 v5.4 forward evidence + IP2 v2.4 live PEP 의무."


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(default="", max_length=20000)


class ChatCompletionRequest(BaseModel):
    model_id: str = Field(default=BUTLER_1_7B_V4_RT.model_id)
    messages: list[ChatMessage]
    routing_context: dict[str, Any] | None = None


def request_digest(payload: ChatCompletionRequest) -> str:
    digest_payload = {
        "model_id": payload.model_id,
        "message_count": len(payload.messages),
        "message_digests": [hashlib.sha256(m.content.encode("utf-8")).hexdigest() for m in payload.messages],
        "routing_context_keys": sorted((payload.routing_context or {}).keys()),
    }
    encoded = json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def build_dry_run_completion(payload: ChatCompletionRequest, digest: str) -> dict[str, Any]:
    model_status_level = BUTLER_1_7B_V4_RT.model_status_level
    forward_verified = BUTLER_1_7B_V4_RT.forward_verified
    routing_executable = BUTLER_1_7B_V4_RT.routing_executable

    actual_model_call = False
    production_hook_deployed = False
    release_claim_allowed = False

    if model_status_level == "artifact_sealed" and not forward_verified and not routing_executable:
        routing_state = "dry_run"
        reason_code = "model_status_level_artifact_sealed"
    else:
        routing_state = "blocked"
        reason_code = "non_executable_routing_guard"

    return {
        "id": f"chatcmpl-dryrun-{digest[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "sample replay 결과입니다. 실제 모델 호출은 실행되지 않았습니다.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "ip3_routing": {
            "routing_state": routing_state,
            "routing_target": "blocked",
            "actual_model_call": actual_model_call,
            "production_hook_deployed": production_hook_deployed,
            "release_claim_allowed": release_claim_allowed,
            "request_digest": digest,
            "audit_digest": hashlib.sha256((digest + reason_code).encode("utf-8")).hexdigest(),
            "raw_text_persisted": False,
            "reason_code": reason_code,
            "block_message": BLOCK_MESSAGE,
        },
    }


@router.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})
    digest = request_digest(payload)
    return build_dry_run_completion(payload, digest)
