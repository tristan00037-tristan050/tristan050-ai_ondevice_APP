from __future__ import annotations

from .adapters.helper3_format_adapter import apply_format_contract
from .adapters.helper4_grounding_adapter import verify_grounding
from .adapters.helper7_extract_adapter import extract_evidence_units
from .adapters.helper8_style_adapter import apply_style_contract
from .asset_manifest import build_contract_only_asset_manifest, manifest_allows_real
from .draft_service import compose_box3_current_contract_input, draft_from_current_contract
from .security import assert_no_raw_persistence, assert_runtime_text_safe, sha256_digest
from .types import Box3Citation, Box3Format, Box3PipelineResult, Box3Request, Box3Style


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


def _format_style_fail_class(format_result: Box3Format, style_result: Box3Style) -> str | None:
    """helper3 format / helper8 style fail-closed gate (Codex P1 정정, 2026-06-01, PR #770).

    adapter 가 이미 계산한 boolean(required_sections_present / forbidden_style_zero)만으로
    판정한다 — 새 threshold 를 추정하지 않는다. format_match_score: 0.0 또는
    forbidden_style_zero: false 인 draft 가 status="real" 로 통과하던 결함을 차단한다.
    """
    if not format_result["required_sections_present"]:
        return "FORMAT_MATCH_BELOW_GATE"
    if not style_result["forbidden_style_zero"]:
        return "FORBIDDEN_STYLE_DETECTED"
    return None


def run_box3_pipeline(
    request: Box3Request,
    *,
    asset_manifest: dict | None = None,
    injected_unsupported_claim_count: int = 0,
    real_model_runner=None,
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
    runner = real_model_runner if real_allowed else None
    draft_response = draft_from_current_contract(**contract_input, real_model_runner=runner)
    draft_was_real = (
        draft_response.get("status") == "real"
        and draft_response.get("contract_only") is False
        and draft_response.get("real_claim_allowed") is True
    )
    draft_basis_text = (
        str(draft_response["draft_text"])
        if draft_was_real and draft_response.get("draft_text")
        else _contract_draft_text(len(evidence_units))
    )
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
    format_result = apply_format_contract(draft_basis_text)
    style_result = apply_style_contract(draft_basis_text)
    # Codex P1 정정 (2026-06-01, PR #770): fail_class 가 grounding + draft 만 고려하여 helper3/helper8
    # fail-closed 신호(required_sections_present=False, forbidden_style_zero=False)를 무시한 채
    # status="real" 을 통과시키던 결함. format/style adapter 결과를 fail_class 산정에 명시 포함한다.
    format_style_fail = _format_style_fail_class(format_result, style_result)
    fail_class = grounding_fail or draft_response.get("fail_class") or format_style_fail
    status = "real" if real_allowed and draft_was_real and fail_class is None else "contract_only"
    if grounding_fail:
        status = "needs_review" if grounding_fail != "GROUNDING_REFERENCE_COVERAGE_LOW" else "blocked"
    real_claim_allowed = status == "real" and real_allowed and draft_was_real and fail_class is None
    contract_only = not real_claim_allowed
    result: Box3PipelineResult = {
        "status": status,
        "draft_text": draft_basis_text if real_claim_allowed else None,
        "draft_digest": sha256_digest(draft_basis_text),
        "citations": citations,
        "grounding": grounding,
        "format": format_result,
        "style": style_result,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_doc_logged": False,
        "fail_class": fail_class,
        "contract_only": contract_only,
        "real_claim_allowed": real_claim_allowed,
    }
    assert_no_raw_persistence(result)
    return result
