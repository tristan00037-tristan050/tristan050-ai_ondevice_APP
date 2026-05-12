"""deadline_types.py — 단계 6.5.4 Patch A+B (알고리즘 팀 §6).

Patch A: DeadlineType Enum (6종) — deadline-like 표현의 의미 분류.
Patch B: disqualifier 패턴 + classify_deadline_candidate.

Verifier(Block 7)가 type을 기준으로 차단:
  - HARD_DEADLINE / SOFT_DEADLINE → 유효 deadline
  - DEADLINE_INQUIRY / URGENCY / CONDITION / NONE → deadline 아님 (block)
"""
from __future__ import annotations

from enum import Enum
from typing import List


class DeadlineType(str, Enum):
    NONE              = "none"
    HARD_DEADLINE     = "hard_deadline"      # 금요일까지, 5월 10일까지
    SOFT_DEADLINE     = "soft_deadline"      # 오늘 중, 이번 주 중
    DEADLINE_INQUIRY  = "deadline_inquiry"   # 언제까지 가능?
    URGENCY           = "urgency"            # 지금 바로, ASAP
    CONDITION         = "condition"          # 완료되면, 확인되면


DEADLINE_INQUIRY_PATTERNS: List[str] = [
    "언제까지 가능",
    "언제까지 될까요",
    "언제까지 가능하신가요",
    "기한이 어떻게",
    "마감이 언제",
]

URGENCY_ONLY_PATTERNS: List[str] = [
    "지금 바로",
    "바로",
    "즉시",
    "가능한 빨리",
    "ASAP",
]

CONDITION_ONLY_PATTERNS: List[str] = [
    "완료되면",
    "확인되면",
    "정리되면",
    "준비되면",
    "수정이 완료되면",
]


def classify_deadline_candidate(text: str) -> DeadlineType:
    """text 내 deadline-like 표현 → DeadlineType.

    우선순위:
      1. DEADLINE_INQUIRY  (질문형 — 언제까지 가능?)
      2. CONDITION         (조건절 — 완료되면)
      3. URGENCY           (긴급 — 지금 바로)
      4. HARD_DEADLINE     ("까지" / "전까지")
      5. SOFT_DEADLINE     ("중으로" / "오늘 중" / "이번 주 중")
      6. NONE              (위 패턴 없음)
    """
    if not text:
        return DeadlineType.NONE
    if any(p in text for p in DEADLINE_INQUIRY_PATTERNS):
        return DeadlineType.DEADLINE_INQUIRY
    if any(p in text for p in CONDITION_ONLY_PATTERNS):
        return DeadlineType.CONDITION
    if any(p in text for p in URGENCY_ONLY_PATTERNS):
        return DeadlineType.URGENCY
    if "까지" in text or "전까지" in text:
        return DeadlineType.HARD_DEADLINE
    if "중으로" in text or "오늘 중" in text or "이번 주 중" in text:
        return DeadlineType.SOFT_DEADLINE
    return DeadlineType.NONE


def is_valid_deadline_type(dtype: DeadlineType) -> bool:
    """Verifier에서 통과시킬 type 집합 — HARD/SOFT_DEADLINE 만."""
    return dtype in {DeadlineType.HARD_DEADLINE, DeadlineType.SOFT_DEADLINE}
