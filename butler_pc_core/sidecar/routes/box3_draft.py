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
from butler_pc_core.cards.box3.endpoint_wiring import (
    Box3EndpointWiringError,
    run_box3_endpoint_wiring,
)
from butler_pc_core.cards.box3.security import Box3SecurityError
from butler_pc_core.model_tier.shadow_observer import (
    complete_box3_shadow_best_effort,
    prepare_box3_shadow_best_effort,
    response_digest_best_effort,
)

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

    request_digest = digest_payload(payload)
    reference_count = len(payload.reference_docs) if payload.reference_docs else int(bool(payload.input_text))
    input_chars = (
        sum(len(doc) for doc in payload.reference_docs) + len(payload.drafting_request or "")
        if payload.reference_docs
        else len(payload.input_text or "") + len(payload.prompt_template or "")
    )
    try:
        shadow_pre_context = prepare_box3_shadow_best_effort(
            request_digest=request_digest,
            facts={
            "payload_digest": request_digest,
            "input_chars": input_chars,
            "attachment_count": reference_count,
            "total_attachment_bytes": (
                sum(len(doc.encode("utf-8")) for doc in payload.reference_docs)
                if payload.reference_docs
                else len((payload.input_text or "").encode("utf-8"))
            ),
            "requested_output_tokens": payload.max_new_tokens,
            "reference_count": reference_count,
            "structured_output_required": bool(
                payload.reference_docs and payload.format_hint != "자유형"
            ),
            "deterministic_path_available": False,
            "ambiguity_score": 0.5,
            },
        )
    except Exception:
        shadow_pre_context = None

    # actual endpoint wiring 경로 (PR #778 정정): sealed approval pre-gate 가 runner 연결을
    # 결정한다 — request/UI flag 는 real 승인으로 사용하지 않음. approval false → contract_only,
    # approval true + 9 조건 + helper_component_use → PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL,
    # runtime unavailable → PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE. 본진 legacy contract /
    # response 필드 보존 (response.request_digest · raw_doc_logged 등).
    if payload.reference_docs and payload.drafting_request:
        try:
            response = run_box3_endpoint_wiring(
                reference_docs=list(payload.reference_docs),
                drafting_request=payload.drafting_request,
                format_hint=payload.format_hint,
                max_new_tokens=payload.max_new_tokens,
                policy_gate_allowed=bool(getattr(request.state, "policy_gate_allowed", True)),
            )
        except Box3SecurityError as exc:
            raise HTTPException(
                status_code=422,
                detail={"fail_class": "BLOCK_BOX3_REAL_SECURITY_RISK", "reason_code": str(exc)},
            )
        except (Box3EndpointWiringError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"fail_class": str(exc) or exc.__class__.__name__},
            ) from exc
        response["request_digest"] = request_digest
        response["raw_doc_logged"] = False
        try:
            complete_box3_shadow_best_effort(
                pre_context=shadow_pre_context,
                actual_response_digest=response_digest_best_effort(response),
                fail_class=str(response.get("fail_class") or "") or None,
                quality_vector={
                    "citation_count": len(response.get("citations") or []),
                    "draft_present": bool(response.get("draft_text") or response.get("초안")),
                    "needs_review": bool(response.get("needs_review")),
                },
            )
        except Exception:
            pass
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
    result_dict["request_digest"] = request_digest
    result_dict["sealed_sha"] = SEALED_SHA
    result_dict["raw_doc_logged"] = False
    try:
        complete_box3_shadow_best_effort(
            pre_context=shadow_pre_context,
            actual_response_digest=response_digest_best_effort(result_dict),
            fail_class=str(result_dict.get("fail_class") or "") or None,
            quality_vector={"draft_present": bool(result_dict.get("draft_text"))},
        )
    except Exception:
        pass
    return result_dict
