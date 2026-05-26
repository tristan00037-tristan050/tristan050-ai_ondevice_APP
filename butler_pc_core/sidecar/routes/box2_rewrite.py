from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from butler_pc_core.cards.box2.rewrite_service import RewriteOptions, rewrite_to_company_format

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_DOC_LENGTH = 12000
MAX_FORMAT_LENGTH = 12000


class Box2RewriteOptions(BaseModel):
    tone: Literal["company_standard", "formal", "plain"] = "company_standard"
    preserve_numbers: bool = True
    redact_sensitive: bool = True


class Box2RewriteRequest(BaseModel):
    foreign_doc: str = Field(..., min_length=1, max_length=MAX_DOC_LENGTH)
    our_format: str = Field(..., min_length=1, max_length=MAX_FORMAT_LENGTH)
    options: Box2RewriteOptions = Field(default_factory=Box2RewriteOptions)


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def digest_payload(payload: Box2RewriteRequest) -> str:
    digest_source = {
        "foreign_doc_sha256": hashlib.sha256(payload.foreign_doc.encode("utf-8")).hexdigest(),
        "our_format_sha256": hashlib.sha256(payload.our_format.encode("utf-8")).hexdigest(),
        "options": payload.options.model_dump(),
    }
    encoded = json.dumps(digest_source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@router.post("/v1/cards/2/rewrite")
async def rewrite_box2(payload: Box2RewriteRequest, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    service_options = RewriteOptions(
        tone=payload.options.tone,
        preserve_numbers=payload.options.preserve_numbers,
        redact_sensitive=payload.options.redact_sensitive,
    )
    result = rewrite_to_company_format(payload.foreign_doc, payload.our_format, service_options)
    result_dict = result.__dict__.copy()
    result_dict["request_digest"] = digest_payload(payload)
    result_dict["external_send_zero"] = True
    result_dict["raw_saved_zero"] = True
    result_dict["raw_doc_logged"] = False
    return result_dict
