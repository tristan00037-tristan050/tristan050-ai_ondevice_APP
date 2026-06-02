from __future__ import annotations

from .adapters.helper3_format_adapter import apply_format_contract
from .adapters.helper4_grounding_adapter import verify_grounding
from .adapters.helper7_extract_adapter import extract_evidence_units
from .adapters.helper8_style_adapter import apply_style_contract
from .asset_manifest import build_contract_only_asset_manifest, manifest_allows_real, manifest_block_reason
from .draft_service import (
    CLAIM_LEVEL_GROUNDING_IMPLEMENTED,
    compose_box3_current_contract_input,
    draft_from_current_contract,
)
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


# real 진입은 claim-level grounding 이 구현(CLAIM_LEVEL_GROUNDING_IMPLEMENTED=True)된 뒤에만 가능
# 하다(draft_service 정의). pipeline 의 verify_grounding 은 synthetic citation(digest-link)만
# 검사하고 draft claim 을 evidence 와 대조하지 않으므로, 그 전까지 real path 를 fail-closed 로 막는다.
def box3_real_claim_allowed(
    *,
    real_allowed: bool,
    draft_was_real: bool,
    real_draft_text,
    grounding_fail,
    format_result: Box3Format,
    style_result: Box3Style,
    claim_level_grounding_verified: bool = CLAIM_LEVEL_GROUNDING_IMPLEMENTED,
) -> bool:
    """box3 real 진입 단일 게이트 (Codex 근본 재검토, 2026-06-01, PR #770).

    real 주장은 아래 축이 모두 충족될 때만 허용된다(AND). 하나라도 미충족이면 False →
    호출부는 contract_only / real_claim=false / draft_text=None 으로 fail-closed 한다.
      (1) asset_status == ASSET_INVENTORY_PASS  ┐
      (7) manifest 유효: 4개 필수 자산 정확 1회 + 각 row 유효  ├ real_allowed = manifest_allows_real
      (8) interface_inventory_status == "pass"  ┘
      (2) runner 실제 실행: draft_was_real
      (3) grounding pass: grounding_fail is None
      (6) non-empty real draft
      (4) format pass: required_sections_present
      (5) style pass: forbidden_style_zero
    개별 엣지(#A empty / #B status drift / #C 자산이름·중복 / #D interface)는 모두 본 축으로
    흡수되므로, CONTRACT_ONLY(asset PENDING)에서는 real 내부 엣지에 도달하지 않는다.
    """
    return bool(
        claim_level_grounding_verified  # claim-level grounding 미구현 시 real 차단(fail-closed)
        and real_allowed
        and draft_was_real
        and grounding_fail is None
        and str(real_draft_text or "").strip()
        and format_result["required_sections_present"]
        and style_result["forbidden_style_zero"]
    )


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
    manifest = build_contract_only_asset_manifest() if asset_manifest is None else asset_manifest
    manifest_fail_class = manifest_block_reason(manifest)
    if manifest_fail_class:
        result: Box3PipelineResult = {
            "status": "blocked",
            "draft_text": None,
            "draft_digest": None,
            "citations": [],
            "grounding": {
                "reference_coverage": 0.0,
                "grounding_pass_rate": 0.0,
                "unsupported_claim_rate": 0.0,
                "contradiction_count": 0,
                "source_digest_coverage": 0.0,
            },
            "format": apply_format_contract(None),
            "style": apply_style_contract(None),
            "external_send_zero": True,
            "raw_saved_zero": True,
            "raw_doc_logged": False,
            "fail_class": manifest_fail_class,
            "contract_only": True,
            "real_claim_allowed": False,
        }
        assert_no_raw_persistence(result)
        return result
    real_allowed = manifest_allows_real(manifest)
    evidence_units = extract_evidence_units(request.reference_docs)
    reference_doc_digests = [unit.source_digest for unit in evidence_units]
    if not reference_doc_digests:
        result: Box3PipelineResult = {
            "status": "needs_review",
            "draft_text": None,
            "draft_digest": None,
            "citations": [],
            "grounding": {
                "reference_coverage": 0.0,
                "grounding_pass_rate": 0.0,
                "unsupported_claim_rate": 0.0,
                "contradiction_count": 0,
                "source_digest_coverage": 0.0,
            },
            "format": apply_format_contract(None),
            "style": apply_style_contract(None),
            "external_send_zero": True,
            "raw_saved_zero": True,
            "raw_doc_logged": False,
            "fail_class": "NO_EVIDENCE_UNITS",
            "contract_only": True,
            "real_claim_allowed": False,
        }
        assert_no_raw_persistence(result)
        return result
    contract_input = compose_box3_current_contract_input(
        reference_doc_digests=reference_doc_digests,
        request_digest=sha256_digest(request.draft_request),
        format_hint=request.format_hint,
        max_new_tokens=request.max_new_tokens,
    )
    # Codex P1 정정 (2026-06-01, PR #770): real 이 구조적으로 불가(claim-level grounding 미구현)인데
    # runner 를 호출하면 결과가 어차피 contract_only 로 demote 됨에도 모델이 실제 실행되어
    # external_send_zero 가 runner 동작에 좌우된다. real 승격 가능 조건(real_allowed AND
    # CLAIM_LEVEL_GROUNDING_IMPLEMENTED)에서만 runner 를 선택한다 — 그 전엔 runner 미호출(fail-closed).
    runner = real_model_runner if (real_allowed and CLAIM_LEVEL_GROUNDING_IMPLEMENTED) else None
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
    # Codex P2 정정 (2026-06-01, PR #770): draft 검사 전 모든 evidence 를 "supported" 로 제조하면
    # verify_grounding 이 합성 citation 만 보고 unsupported claim 을 탐지 못한 채 status="real" 을
    # 내주는 과대주장이 된다. CONTRACT_ONLY 스코프에서 citation 은 digest 연결만 의미하므로
    # "digest_linked" 로 표기한다. draft claim 추출·evidence 대조 supported/unsupported 실판정(real
    # grounding 추출)은 real 단계 후속 PR 범위다(runner 차단 + digest_linked = 실제 검증 0, real 후속).
    citations: list[Box3Citation] = [
        {
            "source_digest": unit.source_digest,
            "evidence_unit_digest": unit.unit_digest,
            "support_level": "digest_linked",
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
    # Codex 근본 재검토 (2026-06-01, PR #770): real 진입을 단일 게이트(box3_real_claim_allowed)로
    # 중앙화. 8축(asset PASS + manifest 유효 + interface PASS ← real_allowed / runner 실행 /
    # grounding / non-empty / format / style)을 AND. 하나라도 미충족이면 real 불가 → contract_only
    # / real_claim=false / draft_text=None. 개별 엣지(#A~#D)는 본 게이트 축으로 흡수.
    real_claim_allowed = box3_real_claim_allowed(
        real_allowed=real_allowed,
        draft_was_real=draft_was_real,
        real_draft_text=draft_response.get("draft_text"),
        grounding_fail=grounding_fail,
        format_result=format_result,
        style_result=style_result,
    )
    # fail_class 는 보고용(우선순위 보존: grounding > draft 계약 > format/style > empty-real).
    real_draft_empty = draft_was_real and not str(draft_response.get("draft_text") or "").strip()
    if real_claim_allowed:
        status, fail_class = "real", None
    else:
        fail_class = (
            grounding_fail
            or draft_response.get("fail_class")
            or _format_style_fail_class(format_result, style_result)
            or ("REAL_DRAFT_EMPTY" if real_draft_empty else None)
        )
        if grounding_fail:
            status = "needs_review" if grounding_fail != "GROUNDING_REFERENCE_COVERAGE_LOW" else "blocked"
        else:
            status = "contract_only"
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
