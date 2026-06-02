"""융합 grounding — 4판정(supported/unsupported/no_evidence/non_claim) + 사실대조."""
from __future__ import annotations

from butler_pc_core.cards.box3.real_contracts import ClaimVerdict, sha256_text
from butler_pc_core.cards.box3.real_grounding import (
    extract_claims,
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)


def _verdicts(reference: str, draft: str):
    units = extract_evidence_units([reference])
    claims = extract_claims(draft)
    return ground_claims(claims, units)


def test_supported_claim_is_evidence_entails_with_citation():
    ref = "프로젝트 알파 납품 일정 표 | 납품일 2026년 3월 31일 | 계약 금액 1억원 | 담당자 검토 완료"
    verdicts = _verdicts(ref, "핵심 내용: 납품일 2026년 3월 31일 계약 금액 1억원")
    supported = [v for v in verdicts if v.support_level == "supported"]
    assert supported and supported[0].reason_code == "EVIDENCE_ENTAILS"
    assert supported[0].evidence_digests and supported[0].evidence_digests[0].startswith("sha256:")


def test_numeric_or_fact_mismatch_is_unsupported_contradicts():
    ref = "계약 금액은 1억원으로 합의되었다."
    verdicts = _verdicts(ref, "핵심 내용: 계약 금액은 5억원으로 합의되었다")
    assert any(
        v.support_level == "unsupported" and v.reason_code == "EVIDENCE_CONTRADICTS" for v in verdicts
    )


def test_negation_contradiction_is_unsupported():
    ref = "프로젝트 알파 납품 일정 계약 금액 담당자 검토 완료 승인되었다."
    verdicts = _verdicts(ref, "핵심 내용: 프로젝트 알파 납품 일정 계약 금액 담당자 검토 완료 승인 불가")
    assert any(v.support_level == "unsupported" for v in verdicts)


def test_unrelated_factual_claim_is_no_evidence():
    ref = "프로젝트 알파 납품 일정 보고."
    verdicts = _verdicts(ref, "핵심 내용: 신규 채용 계획 인원 수량 매출 목표 검토 요청")
    assert any(
        v.support_level == "no_evidence" and v.reason_code == "NO_MATCHING_EVIDENCE" for v in verdicts
    )


def test_non_factual_section_is_non_claim():
    verdicts = _verdicts("배경 자료.", "제목: 보고서\n확인 필요: 없음")
    assert all(
        v.support_level == "non_claim" and v.reason_code == "NON_FACTUAL" for v in verdicts
    )


def test_summary_no_evidence_within_threshold_is_verified():
    # 1/20 = 0.05 → SSOT 임계 내 → 요약 fail_class None(stage_trace 모순 방지).
    supported = [
        ClaimVerdict(f"c{i}", sha256_text(f"c{i}"), "supported", ["sha256:" + "a" * 64], 0.9, "EVIDENCE_ENTAILS")
        for i in range(19)
    ]
    no_evidence = [ClaimVerdict("c19", sha256_text("c19"), "no_evidence", [], 0.0, "NO_MATCHING_EVIDENCE")]
    summary = summarize_grounding(supported + no_evidence)
    assert summary.no_evidence_rate == 0.05
    assert summary.fail_class is None
    assert summary.claim_grounding_verified is True


def test_summary_no_evidence_above_threshold_flags_review():
    supported = [
        ClaimVerdict(f"c{i}", sha256_text(f"c{i}"), "supported", ["sha256:" + "a" * 64], 0.9, "EVIDENCE_ENTAILS")
        for i in range(18)
    ]
    no_evidence = [
        ClaimVerdict(f"n{i}", sha256_text(f"n{i}"), "no_evidence", [], 0.0, "NO_MATCHING_EVIDENCE")
        for i in range(2)
    ]
    summary = summarize_grounding(supported + no_evidence)
    assert summary.no_evidence_rate > 0.05
    assert summary.fail_class == "NEEDS_REVIEW_NO_EVIDENCE_CLAIM"


def test_summary_counts_and_citation_accuracy():
    ref = "프로젝트 알파 납품 일정 표 | 납품일 2026년 3월 31일 | 계약 금액 1억원 | 담당자 검토 완료 합의 완료"
    draft = (
        "배경: 프로젝트 알파 납품 일정 보고\n"
        "핵심 내용: 납품일 2026년 3월 31일 계약 금액 1억원\n"
        "근거: 담당자 검토 완료 합의 완료\n"
    )
    summary = summarize_grounding(_verdicts(ref, draft))
    assert summary.unsupported_claim_count == 0
    assert summary.citation_accuracy == 1.0
    assert summary.claim_grounding_verified is True
    assert summary.fail_class is None
