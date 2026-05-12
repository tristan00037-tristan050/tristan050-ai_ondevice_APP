"""verifier.py — 원문 근거 검증 + hallucination 차단 (알고리즘 팀 §6-6, §11)."""
from __future__ import annotations

from typing import Tuple

from .contracts import Card1Extraction, ExtractedAction, SentenceType
from .parser import ACTION_VERBS, _ACTION_VERB_RE


def verify_card1_extraction(
    extraction: Card1Extraction,
    source_text: str,
) -> Tuple[Card1Extraction, int]:
    """
    원문 근거 검증 → (정정된 Card1Extraction, hallucination 개수).

    Block 기준 (알고리즘 팀 §11):
      1. 원문에 없는 마감일 표현  → deadline/deadline_raw 초기화
      2. 원문에 없는 자료명       → materials에서 제거
      3. 부정형 문장을 액션으로   → actions 전체 제거
      4. 액션 동사 없는 문장을 액션으로 → 해당 액션 제거
    """
    hallucination_count = 0

    # Block 1: 마감일 원문 근거 없음
    deadline_raw = extraction.deadline_raw
    if deadline_raw and deadline_raw not in source_text:
        extraction = _replace(extraction, deadline=None, deadline_raw="")
        hallucination_count += 1

    # Block 2: 자료 원문 근거 없음
    verified_materials = []
    for mat in extraction.materials:
        if mat in source_text:
            verified_materials.append(mat)
        else:
            hallucination_count += 1

    # Block 3: 부정형 문장 전체 → 액션 제거
    if extraction.sentence_type == SentenceType.NEGATIVE:
        hallucination_count += len(extraction.actions)
        extraction = _replace(extraction, materials=verified_materials, actions=[])
        return extraction, hallucination_count

    # Block 4: 액션 동사 없는 액션 항목 제거
    verified_actions = []
    for action in extraction.actions:
        evidence = action.source_evidence or action.action_text
        if _ACTION_VERB_RE.search(evidence) or _ACTION_VERB_RE.search(source_text):
            verified_actions.append(action)
        else:
            hallucination_count += 1

    extraction = _replace(
        extraction,
        materials=verified_materials,
        actions=verified_actions,
    )
    return extraction, hallucination_count


def _replace(extraction: Card1Extraction, **kwargs) -> Card1Extraction:
    """Card1Extraction 필드 부분 교체 (dataclass replace 패턴)."""
    return Card1Extraction(
        intent        = kwargs.get("intent",        extraction.intent),
        intent_type   = kwargs.get("intent_type",   extraction.intent_type),
        deadline      = kwargs.get("deadline",      extraction.deadline),
        deadline_raw  = kwargs.get("deadline_raw",  extraction.deadline_raw),
        materials     = kwargs.get("materials",     extraction.materials),
        actions       = kwargs.get("actions",       extraction.actions),
        sentence_type = kwargs.get("sentence_type", extraction.sentence_type),
        confidence    = kwargs.get("confidence",    extraction.confidence),
        needs_review  = kwargs.get("needs_review",  extraction.needs_review),
        reason_code   = kwargs.get("reason_code",   extraction.reason_code),
    )
