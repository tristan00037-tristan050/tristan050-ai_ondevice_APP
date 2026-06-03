from __future__ import annotations

from butler_pc_core.cards.box3.real_eval import build_canonical_fixed_eval_cases, evaluate_fixed_eval_cases
from butler_pc_core.cards.box3.real_grounding import extract_claims, extract_evidence_units, ground_claims, summarize_grounding


def test_alg_fixed_eval_40_cases_verdict_only_pass():
    cases = build_canonical_fixed_eval_cases()
    result = evaluate_fixed_eval_cases(cases)
    assert len(cases) == 40
    assert result.case_count == 40
    assert result.failed_count == 0
    assert result.passed is True
    assert result.raw_saved_zero is True


def test_number_contradiction_regression():
    evidence = extract_evidence_units(["금액은 120만원입니다."])
    claims = extract_claims("핵심 내용: 금액은 130만원입니다.")
    summary = summarize_grounding(ground_claims(claims, evidence))
    assert summary.unsupported_claim_count == 1


def test_negation_contradiction_regression():
    evidence = extract_evidence_units(["해당 요청은 승인되었습니다."])
    claims = extract_claims("핵심 내용: 해당 요청은 미승인 상태입니다.")
    summary = summarize_grounding(ground_claims(claims, evidence))
    assert summary.unsupported_claim_count >= 1
