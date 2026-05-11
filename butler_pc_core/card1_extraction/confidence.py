"""confidence.py — evidence 기반 신뢰도 산출 (알고리즘 팀 §6-6)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceFactors:
    action_verb_count:  int   = 0     # ACTION_VERBS 원문 히트 수
    deadline_found:     bool  = False  # DEADLINE_PATTERNS 원문 매칭 여부
    deadline_claimed:   bool  = False  # 마감 주장 여부 (LLM/파서 출력)
    material_count:     int   = 0     # 원문 근거 있는 자료 수
    action_count:       int   = 0     # 원문 근거 있는 액션 수
    hallucination_count: int  = 0     # 원문 근거 없는 항목 수 (verifier 판정)


_BASE_SCORE = 0.40


def compute_card1_confidence(factors: ConfidenceFactors) -> float:
    """
    evidence 기반 신뢰도 계산.

    구성:
      base                          = 0.40
      의도 근거 (ACTION_VERBS 히트)   → +0.25
      마감 근거 (DEADLINE_PATTERNS)   → +0.25 (근거 없이 주장 시 -0.20)
      자료 근거                       → +0.05 × hits (max 0.20)
      액션 근거                       → +0.05 × hits (max 0.20)
      hallucination penalty          → -0.20 × count

    구간 (§6-6):
      0.90+     : 자동 적용
      0.75~0.89 : 확인 배지
      0.60~0.74 : 사용자 확인 필요
      0.60 미만  : 자동 적용 X
    """
    score = _BASE_SCORE

    if factors.action_verb_count > 0:
        score += 0.25

    if factors.deadline_found:
        score += 0.25
    elif factors.deadline_claimed:
        score -= 0.20

    score += min(factors.material_count * 0.05, 0.20)
    score += min(factors.action_count   * 0.05, 0.20)
    score -= factors.hallucination_count * 0.20

    return round(max(0.0, min(1.0, score)), 3)


def confidence_band(confidence: float) -> str:
    """신뢰도 수치 → 구간 레이블."""
    if confidence >= 0.90:
        return "auto"
    if confidence >= 0.75:
        return "badge"
    if confidence >= 0.60:
        return "confirm"
    return "blocked"
