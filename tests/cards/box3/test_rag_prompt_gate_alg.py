"""ALG rag_prompt gate 정합 (PR #781, 2026-06-04) — MAINDEV grounded_prompt
``evaluate_usefulness_gate`` SSOT 위에서 ALG PASS/PARTIAL/BLOCK 케이스를 잠근다.

단일 경로 정책: ALG 측의 별도 ``rag_prompt.analyze_rag_prompt_gate`` 진입점은 도입하지
않고, MAINDEV ``grounded_prompt.evaluate_usefulness_gate`` 가 동일 PASS/PARTIAL/BLOCK
의무를 충족함을 회귀 잠금한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from butler_pc_core.cards.box3.grounded_prompt import (
    ABSTAINED_SLOT_TEXT,
    evaluate_usefulness_gate,
)


@dataclass
class V:
    support_level: str


GOOD_DRAFT = """제목: 참고 기반 초안 (근거1)
배경: 납품 일정은 2026년 6월 10일입니다. (근거1)
핵심내용: 일정은 근거 문서 기준으로 검토합니다. (근거1)
근거: [근거1] source_digest citation
확인필요: 담당자는 [문서에 근거 없음]
최종문안: 납품 일정 기준으로 진행합니다. (근거1)
"""


def test_pass_requires_useful_supported_claims_and_sections():
    verdict = evaluate_usefulness_gate(
        GOOD_DRAFT,
        claim_verdicts=[V("supported"), V("supported")],
    )
    assert verdict.status == "PASS"
    assert verdict.fail_class is None


def test_unsupported_claim_blocks_even_if_sections_present():
    verdict = evaluate_usefulness_gate(
        GOOD_DRAFT,
        claim_verdicts=[V("supported"), V("unsupported")],
    )
    assert verdict.status == "BLOCK"
    assert verdict.fail_class == "BLOCK_UNSUPPORTED_CLAIM"


def test_abstain_overuse_is_partial_not_pass():
    abstain_lines = "\n".join(f"확인필요: {ABSTAINED_SLOT_TEXT}" for _ in range(6))
    draft = GOOD_DRAFT + "\n" + abstain_lines
    verdict = evaluate_usefulness_gate(
        draft,
        claim_verdicts=[V("supported"), V("supported")],
    )
    assert verdict.status == "PARTIAL"
    assert verdict.fail_class == "PARTIAL_ABSTAIN_OVERUSE"


def test_empty_draft_cannot_pass_by_unsupported_zero():
    verdict = evaluate_usefulness_gate("", claim_verdicts=[])
    assert verdict.status == "PARTIAL"
    assert verdict.fail_class == "PARTIAL_SUPPORTED_CLAIM_COUNT_LOW"


def test_zero_supported_with_no_unsupported_is_partial_not_pass():
    verdict = evaluate_usefulness_gate(
        GOOD_DRAFT,
        claim_verdicts=[V("no_evidence"), V("no_evidence")],
    )
    assert verdict.status == "PARTIAL"
    assert verdict.fail_class == "PARTIAL_SUPPORTED_CLAIM_COUNT_LOW"
