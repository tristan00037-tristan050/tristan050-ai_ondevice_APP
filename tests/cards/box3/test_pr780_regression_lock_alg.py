"""ALG PR #780 regression lock (2026-06-04, PR #781) — PR #780 머지본에서 관측된
1.7B v4-rt 환각 케이스(이름·결재 항목 fabrication)가 RAG·Prompt v1.2 통합 위에서도
gate 에 의해 BLOCK 됨을 잠근다. 또한 grounded prompt 가 absent_slots 를 강제하여
모델이 "[문서에 근거 없음]" 을 사용하도록 유도함을 검증한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from butler_pc_core.cards.box3.grounded_prompt import (
    ABSTAINED_SLOT_TEXT,
    evaluate_usefulness_gate,
)
from butler_pc_core.cards.box3.rag_prompt_integration import build_rag_grounded_prompt_runtime
from butler_pc_core.cards.box3.rag_context import sha256_text


@dataclass
class V:
    support_level: str


class _Envelope:
    drafting_request_runtime_only = "결재자 이름과 결재 항목을 포함해 초안 작성"
    reference_text_runtime_only = [
        "참고문서에는 납품 일정만 2026년 6월 10일로 기재되어 있다."
    ]
    format_hint = "보고서"
    max_new_tokens = 300

    @property
    def request_digest(self):
        return sha256_text("pr780-regression-lock")


def test_pr780_no_name_hallucination_prompt_forces_absent_slot():
    env = _Envelope()
    evidence = SimpleNamespace(
        evidence_units_runtime=[
            SimpleNamespace(
                text_runtime_only="납품 일정은 2026년 6월 10일로 기재되어 있다.",
                source_digest=sha256_text("pr780-doc"),
                evidence_digest=sha256_text("pr780-unit-1"),
                kind="text",
            )
        ]
    )
    result = build_rag_grounded_prompt_runtime(env, evidence)
    prompt = env.grounded_prompt_runtime_only
    # absent_slot 안내 + ABSTAINED_SLOT_TEXT 가 프롬프트에 반드시 포함.
    assert ABSTAINED_SLOT_TEXT in prompt
    assert "[근거1]" in prompt
    # 결재자/이름/담당 슬롯이 absent 로 인식되어야 한다 (지시문이 결재자·결재 항목을 요구).
    assert any(slot in result.rag_context.absent_slots for slot in ("name", "approval", "owner"))


def test_pr780_unsupported_name_claim_remains_blocked_by_gate():
    draft = (
        "제목: 초안\n"
        "배경: 김철수 부장이 결재합니다. (근거1)\n"
        "핵심 내용: 일정은 2026년 6월 10일입니다. (근거1)\n"
        "근거: 근거1\n"
        "확인 필요: 없음\n"
        "최종 문안: 진행합니다.\n"
    )
    verdict = evaluate_usefulness_gate(
        draft,
        claim_verdicts=[V("unsupported"), V("supported"), V("supported")],
    )
    assert verdict.status == "BLOCK"
    assert verdict.fail_class == "BLOCK_UNSUPPORTED_CLAIM"


def test_pr780_fewshot_pack_contains_three_purposes():
    from butler_pc_core.cards.box3.grounded_prompt import default_fewshot_pack

    pack = default_fewshot_pack()
    purposes = {example.purpose for example in pack.examples}
    assert purposes == {"injection_defense", "abstain", "no_name_hallucination"}
    assert len(pack.examples) == 3
