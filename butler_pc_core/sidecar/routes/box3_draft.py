from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from butler_pc_core.cards.box3.draft_service import (
    DEFAULT_MAX_NEW_TOKENS,
    MAX_NEW_TOKENS_LIMIT,
    SEALED_SHA,
    draft_from_existing,
)
from butler_pc_core.cards.box3.real_pipeline import run_box3_real_pipeline
from butler_pc_core.cards.box3.security import Box3SecurityError

router = APIRouter()

LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}
MAX_INPUT_LENGTH = 12000
MAX_PROMPT_TEMPLATE_LENGTH = 2000
MAX_REFERENCE_LENGTH = 20000


class Box3DraftRequest(BaseModel):
    # legacy(무회귀) 계약 — 기존 draft_from_existing 경로.
    input_text: Optional[str] = Field(default=None, max_length=MAX_INPUT_LENGTH)
    prompt_template: Optional[str] = Field(default=None, max_length=MAX_PROMPT_TEMPLATE_LENGTH)
    # real 융합 계약 — 참고문서 + 작성요청. asset PENDING 시 contract_only 로 정직 보류.
    reference_docs: List[str] = Field(default_factory=list, max_length=5)
    drafting_request: Optional[str] = Field(default=None, max_length=MAX_PROMPT_TEMPLATE_LENGTH)
    format_hint: str = "자유형"
    max_new_tokens: int = Field(default=DEFAULT_MAX_NEW_TOKENS, ge=1, le=MAX_NEW_TOKENS_LIMIT)

    @field_validator("reference_docs")
    @classmethod
    def _bound_reference_docs(cls, value: List[str]) -> List[str]:
        # legacy input_text(12KB) 와 동일하게 real 참고문서도 항목별로 fail-closed 상한을 적용한다.
        for doc in value:
            if len(doc) > MAX_REFERENCE_LENGTH:
                raise ValueError("REFERENCE_DOC_TOO_LARGE")
        return value


def is_localhost_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOST_HOSTS


def digest_payload(payload: Box3DraftRequest) -> str:
    digest_source = {
        "input_text_sha256": hashlib.sha256((payload.input_text or "").encode("utf-8")).hexdigest(),
        "prompt_template_sha256": hashlib.sha256((payload.prompt_template or "").encode("utf-8")).hexdigest(),
        "reference_docs_sha256": [
            hashlib.sha256(doc.encode("utf-8")).hexdigest() for doc in payload.reference_docs
        ],
        "drafting_request_sha256": hashlib.sha256((payload.drafting_request or "").encode("utf-8")).hexdigest(),
        "max_new_tokens": payload.max_new_tokens,
    }
    encoded = json.dumps(digest_source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@router.post("/v1/cards/3/draft")
async def draft_box3(payload: Box3DraftRequest, request: Request) -> dict[str, Any]:
    if not is_localhost_request(request):
        raise HTTPException(status_code=403, detail={"fail_class": "LOCALHOST_ONLY", "message": "localhost only"})

    # real 융합 경로 — 참고문서 + 작성요청이 있으면 단일 계약 파이프라인을 실행한다.
    # real_model_runner 를 주입하지 않으므로 asset PENDING 상태에서는 contract_only 로 닫힌다.
    if payload.reference_docs and payload.drafting_request:
        try:
            verdict, audit = run_box3_real_pipeline(
                reference_docs=list(payload.reference_docs),
                drafting_request=payload.drafting_request,
                format_hint=payload.format_hint,
                max_new_tokens=payload.max_new_tokens,
                real_model_runner=None,
            )
        except Box3SecurityError as exc:
            raise HTTPException(
                status_code=422,
                detail={"fail_class": "BLOCK_BOX3_REAL_SECURITY_RISK", "reason_code": str(exc)},
            )
        response = verdict.to_response_dict()
        response["audit"] = audit.to_dict()
        response["request_digest"] = digest_payload(payload)
        response["raw_doc_logged"] = False
        return response

    # legacy(무회귀) 경로 — 기존 contract 유지.
    if not payload.input_text or not payload.prompt_template:
        raise HTTPException(
            status_code=422,
            detail={"fail_class": "BLOCK_BOX3_DRAFT_INPUT_MISSING", "message": "reference_docs+drafting_request or input_text+prompt_template required"},
        )
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
