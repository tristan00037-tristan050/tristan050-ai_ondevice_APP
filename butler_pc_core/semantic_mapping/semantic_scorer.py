"""semantic_scorer.py — 소스 필드 ↔ 타깃 슬롯 의미 유사도 (단계 3)."""
from __future__ import annotations

import re

from .contracts import SourceField, TargetSlot

_STOP_KO = {"의", "와", "과", "이", "가", "을", "를", "은", "는", "에", "도", "로", "하다", "및"}

# 명확한 도메인 동의어만 (business 일반어 오매핑 방지)
_KO_SYNONYMS: list[tuple[set[str], set[str]]] = [
    ({"금액", "비용", "견적", "요금"}, {"예산", "budget", "cost", "fee"}),
    ({"시작일", "착수일", "착수", "마감"}, {"일정", "schedule", "날짜"}),
]


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[가-힣a-zA-Z]+", text.lower())
    return {t for t in tokens if t not in _STOP_KO and len(t) >= 2}


def compute_semantic_score(source: SourceField, target: TargetSlot) -> float:
    """
    소스 레이블 ↔ 타깃 슬롯 의미 유사도 (0.0 ~ 1.0).

    우선순위:
      1. 소스 토큰이 heading 토큰과 완전 교집합 → 1.0
      2. 소스 토큰이 heading 토큰과 ≥ 50% 교집합 → 0.85
      3. 소스 토큰 중 하나가 alias 토큰 집합에 포함 → 0.9
      4. 한국어 비즈니스 동의어 fallback → 0.6
      5. 관계 없음 → 0.0
    """
    src_tokens = _tokenize(source.label)
    if not src_tokens:
        return 0.0

    heading_tokens = _tokenize(target.heading)
    all_alias_tokens: set[str] = set()
    for a in target.aliases:
        all_alias_tokens |= _tokenize(a)

    # 1-2. Heading 토큰 교집합
    heading_shared = src_tokens & heading_tokens
    if heading_shared:
        ratio = len(heading_shared) / max(len(heading_tokens), 1)
        if ratio >= 1.0:
            return 1.0
        if ratio >= 0.5:
            return 0.85

    # 3. Alias 직접 포함
    if src_tokens & all_alias_tokens:
        return 0.9

    # 4. 한국어 비즈니스 동의어 fallback
    for src_side, tgt_side in _KO_SYNONYMS:
        if src_tokens & src_side and (heading_tokens | all_alias_tokens) & tgt_side:
            return 0.6

    return 0.0


def compute_alias_score(source: SourceField, target: TargetSlot) -> float:
    """소스 레이블 토큰이 타깃 alias 집합에 직접 포함되면 1.0, 아니면 0.0."""
    src_tokens = _tokenize(source.label)
    all_alias_tokens: set[str] = set()
    for a in target.aliases:
        all_alias_tokens |= _tokenize(a)
    return 1.0 if src_tokens & all_alias_tokens else 0.0
