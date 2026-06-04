from __future__ import annotations

from dataclasses import dataclass

from .real_grounding import extract_claims, extract_evidence_units, ground_claims, summarize_grounding

@dataclass(frozen=True)
class FixedEvalResult:
    case_count: int
    passed_count: int
    failed_count: int
    mock_result: bool = False
    external_send_zero: bool = True
    raw_saved_zero: bool = True

    @property
    def passed(self) -> bool:
        return self.case_count >= 40 and self.failed_count == 0

    def to_dict(self) -> dict:
        return {
            'case_count': self.case_count,
            'passed_count': self.passed_count,
            'failed_count': self.failed_count,
            'mock_result': self.mock_result,
            'external_send_zero': self.external_send_zero,
            'raw_saved_zero': self.raw_saved_zero,
        }

def build_canonical_fixed_eval_cases() -> list[dict[str, str]]:
    cases = []
    kinds = ['보고서', '제안서', '공문', '요약']
    diffs = ['easy', 'medium', 'hard', 'table', 'figure']
    for i in range(40):
        date = f"2026년 6월 {10 + (i % 10)}일"
        amount = f"{100 + i}만원"
        kind = kinds[i % len(kinds)]
        diff = diffs[i % len(diffs)]
        reference = f"{kind} 참고 문서입니다. 납품 일정은 {date}이며, 금액은 {amount}입니다. 분류={diff}."
        draft = f"제목: {kind} 초안\n핵심 내용: 납품 일정은 {date}입니다.\n근거: 금액은 {amount}입니다."
        cases.append({'case_id': f'box3-fixed-{i+1:02d}', 'reference': reference, 'draft': draft})
    return cases

def evaluate_fixed_eval_cases(cases: list[dict[str, str]] | None = None) -> FixedEvalResult:
    cases = cases or build_canonical_fixed_eval_cases()
    passed = 0
    for case in cases:
        evidence = extract_evidence_units([case['reference']])
        claims = extract_claims(case['draft'])
        verdicts = ground_claims(claims, evidence)
        summary = summarize_grounding(verdicts)
        if summary.unsupported_claim_count == 0 and summary.no_evidence_claim_count == 0 and summary.citation_accuracy >= 0.95:
            passed += 1
    return FixedEvalResult(case_count=len(cases), passed_count=passed, failed_count=len(cases) - passed)
