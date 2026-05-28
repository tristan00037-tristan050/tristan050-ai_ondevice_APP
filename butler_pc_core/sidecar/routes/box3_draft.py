from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from butler_pc_core.cards.box3.draft_service import (
    DEFAULT_MAX_NEW_TOKENS,
    MAX_NEW_TOKENS_LIMIT,
    SEALED_SHA,
    draft_from_existing,
)

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_INPUT_LENGTH = 12000
MAX_PROMPT_TEMPLATE_LENGTH = 2000


class Box3DraftRequest(BaseModel):
    input_text: str = Field(..., min_length=1, max_length=MAX_INPUT_LENGTH)
    prompt_template: str = Field(..., min_length=1, max_length=MAX_PROMPT_TEMPLATE_LENGTH)
    max_new_tokens: int = Field(default=DEFAULT_MAX_NEW_TOKENS, ge=1, le=MAX_NEW_TOKENS_LIMIT)


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def digest_payload(payload: Box3DraftRequest) -> str:
    digest_source = {
        "input_text_sha256": hashlib.sha256(payload.input_text.encode("utf-8")).hexdigest(),
        "prompt_template_sha256": hashlib.sha256(payload.prompt_template.encode("utf-8")).hexdigest(),
        "max_new_tokens": payload.max_new_tokens,
    }
    encoded = json.dumps(digest_source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@router.post("/v1/cards/3/draft")
async def draft_box3(payload: Box3DraftRequest, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    result = draft_from_existing(
        payload.input_text,
        payload.prompt_template,
        max_new_tokens=payload.max_new_tokens,
    )
    result_dict = result.to_dict()
    result_dict["request_digest"] = digest_payload(payload)
    result_dict["sealed_sha"] = SEALED_SHA
    result_dict["raw_doc_logged"] = False
    return result_dict
