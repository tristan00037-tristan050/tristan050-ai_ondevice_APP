"""type_scorer.py — ValueType 호환성 점수 + hard guard (단계 4)."""
from __future__ import annotations

from .contracts import SourceField, TargetSlot, ValueType


def compute_type_score(source: SourceField, target: TargetSlot) -> float:
    """
    소스 감지 타입 ↔ 타깃 허용 타입 호환성 점수.

    - 완전 호환 (detected_type in allowed_types) → 1.0
    - DATE ↔ DATE_RANGE 부분 호환 → 0.45
    - 비호환 → 0.0
    """
    dt = source.detected_type
    allowed = target.allowed_types

    if dt in allowed:
        return 1.0

    # DATE ↔ DATE_RANGE 부분 호환 (기간 슬롯에 특정 날짜가 들어오는 경우 등)
    if (dt == ValueType.DATE and ValueType.DATE_RANGE in allowed) or \
       (dt == ValueType.DATE_RANGE and ValueType.DATE in allowed):
        return 0.45

    return 0.0


def apply_hard_guards(final_score: float, type_score: float) -> float:
    """
    타입 호환성 기반 최종 점수 상한 적용.

    - type_score == 0.0 → final ≤ 0.49  (사실상 unmapped 강제)
    - type_score < 0.5  → final ≤ 0.69  (needs_review 이하 강제)
    """
    if type_score == 0.0:
        return min(final_score, 0.49)
    if type_score < 0.5:
        return min(final_score, 0.69)
    return final_score
