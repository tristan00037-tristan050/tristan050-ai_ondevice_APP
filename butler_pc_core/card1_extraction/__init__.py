"""card1_extraction — Action/Intent Extractor 독립 모듈 (알고리즘 팀 §6)."""
from __future__ import annotations

import os
from typing import Callable, Optional

from .confidence import ConfidenceFactors, compute_card1_confidence
from .contracts import (
    Card1Extraction,
    ExtractedAction,
    IntentType,
    SentenceType,
)
from .llm_extractor import extract_with_llm
from .parser import (
    ACTION_VERBS,
    DEADLINE_PATTERNS,
    MATERIAL_WORDS,
    _ACTION_VERB_RE,
    classify_sentence_type,
    extract_actions_candidates,
    extract_deadlines,
    extract_materials,
)
from .verifier import verify_card1_extraction


def extract_card1(
    source_text: str,
    use_llm: bool = False,
    llm_callable: Optional[Callable[[str], str]] = None,
) -> Card1Extraction:
    """
    원문 텍스트 → Card1Extraction (단계 1~5).

    단계 1: 결정론적 패턴 추출 (마감/액션/자료/문형)
    단계 2: LLM structured extraction (use_llm=True + SKIP_LLM≠true)
    단계 3: verifier — 원문 근거 검증 + hallucination 차단
    단계 4: evidence 기반 신뢰도 산출
    단계 5: needs_review 플래그 설정
    """
    # ── 단계 1: 결정론적 파싱 ─────────────────────────────────────────────────
    deadlines   = extract_deadlines(source_text)
    action_sents = extract_actions_candidates(source_text)
    materials   = extract_materials(source_text)
    sent_type   = classify_sentence_type(source_text)

    parsed_hints = {
        "deadlines": deadlines,
        "actions":   action_sents,
        "materials": materials,
    }

    # ── 단계 2: LLM 또는 heuristic ───────────────────────────────────────────
    use_llm_effective = use_llm and os.environ.get("SKIP_LLM") != "true"
    extraction = extract_with_llm(source_text, parsed_hints, llm_callable if use_llm_effective else None)

    # sentence_type은 결정론적 분류 우선 적용
    extraction = _set_sentence_type(extraction, sent_type)

    # ── 단계 3: verifier ─────────────────────────────────────────────────────
    extraction, hallucination_count = verify_card1_extraction(extraction, source_text)

    # ── 단계 4: 신뢰도 산출 ──────────────────────────────────────────────────
    action_verb_count = len([v for v in ACTION_VERBS if v in source_text])
    factors = ConfidenceFactors(
        action_verb_count   = action_verb_count,
        deadline_found      = len(deadlines) > 0,
        deadline_claimed    = bool(extraction.deadline_raw),
        material_count      = len(extraction.materials),
        action_count        = len(extraction.actions),
        hallucination_count = hallucination_count,
    )
    confidence = compute_card1_confidence(factors)

    # ── 단계 5: needs_review 판정 ─────────────────────────────────────────────
    needs_review = confidence < 0.75
    if confidence >= 0.90:
        reason_code = "high_confidence"
    elif confidence >= 0.75:
        reason_code = "badge"
    elif confidence >= 0.60:
        reason_code = "confirm_required"
    else:
        reason_code = "low_evidence"

    return Card1Extraction(
        intent        = extraction.intent,
        intent_type   = extraction.intent_type,
        deadline      = extraction.deadline,
        deadline_raw  = extraction.deadline_raw,
        materials     = extraction.materials,
        actions       = extraction.actions,
        sentence_type = sent_type,
        confidence    = confidence,
        needs_review  = needs_review,
        reason_code   = reason_code,
    )


def _set_sentence_type(extraction: Card1Extraction, sent_type: SentenceType) -> Card1Extraction:
    return Card1Extraction(
        intent        = extraction.intent,
        intent_type   = extraction.intent_type,
        deadline      = extraction.deadline,
        deadline_raw  = extraction.deadline_raw,
        materials     = extraction.materials,
        actions       = extraction.actions,
        sentence_type = sent_type,
        confidence    = extraction.confidence,
        needs_review  = extraction.needs_review,
        reason_code   = extraction.reason_code,
    )


__all__ = [
    "extract_card1",
    "Card1Extraction",
    "ExtractedAction",
    "IntentType",
    "SentenceType",
    "ConfidenceFactors",
    "compute_card1_confidence",
]
