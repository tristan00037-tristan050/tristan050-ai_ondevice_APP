from __future__ import annotations

from butler_pc_core.cards.box3.real_grounding import (
    extract_claims,
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)


def test_grounding_supported_when_evidence_entails_claim():
    refs = ["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 일정은 2026년 6월 10일입니다.")
    verdicts = ground_claims(claims, evidence)
    summary = summarize_grounding(verdicts)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual[0].support_level == "supported"
    assert summary.unsupported_claim_count == 0
    assert summary.claim_grounding_verified is True


def test_grounding_contradiction_is_unsupported():
    refs = ["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."]
    evidence = extract_evidence_units(refs)
    claims = extract_claims("핵심 내용: 납품 일정은 2026년 6월 20일입니다.")
    verdicts = ground_claims(claims, evidence)
    summary = summarize_grounding(verdicts)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual[0].support_level == "unsupported"
    assert summary.unsupported_claim_count == 1
    assert summary.fail_class == "BLOCK_UNSUPPORTED_CLAIM"


def test_ground_claims_returns_list_not_tuple_and_summary_is_separate():
    evidence = extract_evidence_units(["납품 일정은 2026년 6월 10일입니다."])
    claims = extract_claims("핵심 내용: 납품 일정은 2026년 6월 10일입니다.")
    verdicts = ground_claims(claims, evidence)
    assert isinstance(verdicts, list)
    summary = summarize_grounding(verdicts)
    assert summary.factual_claim_count >= 1


def test_specific_date_evidence_supports_shorter_date_claim_without_false_contradiction():
    evidence = extract_evidence_units(["계약서 본문: 납품 일정은 2026년 6월 10일로 확정되었습니다."])
    claims = extract_claims("핵심 내용: 납품 일정은 6월 10일입니다.")
    verdicts = ground_claims(claims, evidence)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    assert factual[0].support_level == "supported"


def test_no_evidence_marks_grounding_unverified():
    evidence = extract_evidence_units(["참고 문서에는 담당자만 언급되어 있습니다."])
    claims = extract_claims("핵심 내용: 납품 일정은 내부 검토 후 확정됩니다.")
    verdicts = ground_claims(claims, evidence)
    summary = summarize_grounding(verdicts)
    assert any(v.support_level == "no_evidence" for v in verdicts if v.support_level != "non_claim")
    assert summary.claim_grounding_verified is False
