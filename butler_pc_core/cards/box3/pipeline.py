from __future__ import annotations

from .adapters.helper3_format_adapter import apply_format_contract
from .adapters.helper4_grounding_adapter import verify_grounding
from .adapters.helper7_extract_adapter import extract_evidence_units
from .adapters.helper8_style_adapter import apply_style_contract
from .asset_manifest import build_contract_only_asset_manifest, manifest_allows_real
from .draft_service import compose_box3_current_contract_input, draft_from_current_contract
from .security import assert_no_raw_persistence, assert_runtime_text_safe, sha256_digest
from .types import Box3Citation, Box3PipelineResult, Box3Request


def _contract_draft_text(evidence_count: int) -> str:
    return "\n".join(
        [
            "제목: [확인 필요: 제목]",
            "배경: 참고 문서의 digest-linked evidence만 사용합니다.",
            f"핵심 내용: {evidence_count}개 evidence unit 기준으로 초안 후보를 구성합니다.",
            "근거: 각 핵심 문장은 source_digest citation을 요구합니다.",
            "확인 필요: 날짜, 금액, 담당자, 계약 조건은 확정하지 않습니다.",
            "최종 문안: [CONTRACT_ONLY_BOX3_DRAFT_NOT_EXECUTED]",
        ]
    )


def run_box3_pipeline(
    request: Box3Request,
    *,
    asset_manifest: dict | None = None,
    injected_unsupported_claim_count: int = 0,
) -> Box3PipelineResult:
    for raw_doc in request.reference_docs:
        assert_runtime_text_safe(raw_doc)
    assert_runtime_text_safe(request.draft_request)
    manifest = asset_manifest or build_contract_only_asset_manifest()
    real_allowed = manifest_allows_real(manifest)
    evidence_units = extract_evidence_units(request.reference_docs)
    reference_doc_digests = [unit.source_digest for unit in evidence_units]
    contract_input = compose_box3_current_contract_input(
        reference_doc_digests=reference_doc_digests,
        request_digest=sha256_digest(request.draft_request),
        format_hint=request.format_hint,
        max_new_tokens=request.max_new_tokens,
    )
    draft_response = draft_from_current_contract(**contract_input)
    draft_text = _contract_draft_text(len(evidence_units))
    citations: list[Box3Citation] = [
        {
            "source_digest": unit.source_digest,
            "evidence_unit_digest": unit.unit_digest,
            "support_level": "supported",
        }
        for unit in evidence_units
    ]
    grounding, grounding_fail = verify_grounding(
        citations=citations,
        evidence_units=evidence_units,
        injected_unsupported_claim_count=injected_unsupported_claim_count,
    )
    format_result = apply_format_contract(draft_text)
    style_result = apply_style_contract(draft_text)
    fail_class = grounding_fail or draft_response.get("fail_class")
    status = "real" if real_allowed and fail_class is None else "contract_only"
    if grounding_fail:
        status = "needs_review" if grounding_fail != "GROUNDING_REFERENCE_COVERAGE_LOW" else "blocked"
    result: Box3PipelineResult = {
        "status": status,
        "draft_text": draft_text if status != "blocked" else None,
        "draft_digest": sha256_digest(draft_text),
        "citations": citations,
        "grounding": grounding,
        "format": format_result,
        "style": style_result,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_doc_logged": False,
        "fail_class": fail_class,
        "contract_only": not real_allowed,
        "real_claim_allowed": real_allowed,
    }
    assert_no_raw_persistence(result)
    return result

