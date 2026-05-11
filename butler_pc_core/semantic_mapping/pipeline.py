"""pipeline.py — 6단계 의미 매핑 파이프라인 통합 진입점."""
from __future__ import annotations

from typing import List

from .contracts import MappingCandidate, MappingDecision, SourceField, TargetSlot
from .semantic_scorer import compute_alias_score, compute_semantic_score
from .slot_resolver import resolve_slot_assignments
from .type_scorer import apply_hard_guards, compute_type_score
from .value_type_detector import detect_value_type

_W_SEMANTIC = 0.40
_W_TYPE     = 0.35
_W_CONTEXT  = 0.15
_W_ALIAS    = 0.10
_CONTEXT_DEFAULT = 0.5  # 단계 4 (LLM) 도입 전 중립값


def _score_candidate(source: SourceField, target: TargetSlot) -> float:
    """단일 (소스, 슬롯) 쌍의 최종 점수 계산 + hard guard 적용."""
    sem   = compute_semantic_score(source, target)
    typ   = compute_type_score(source, target)
    alias = compute_alias_score(source, target)
    raw   = sem * _W_SEMANTIC + typ * _W_TYPE + _CONTEXT_DEFAULT * _W_CONTEXT + alias * _W_ALIAS
    return apply_hard_guards(raw, typ)


def map_fields(
    source_fields: List[SourceField],
    target_slots: List[TargetSlot],
) -> List[MappingDecision]:
    """
    6단계 의미 매핑 파이프라인.

    단계 1-2: 소스 필드 값 타입 감지
    단계 3-4: semantic_score + type_score 계산
    단계 5:   hard guard 적용
    단계 6:   context_score (현재 0.5 중립) + alias_score
    단계 7:   greedy 슬롯 배정 (slot_resolver)
    """
    # 단계 1-2: 값 타입 자동 감지
    for field in source_fields:
        field.detected_type = detect_value_type(field.label, field.value)

    # 단계 3-6: 전체 후보 행렬 생성 + 점수
    candidates: List[MappingCandidate] = []
    for src in source_fields:
        for tgt in target_slots:
            sem   = compute_semantic_score(src, tgt)
            typ   = compute_type_score(src, tgt)
            alias = compute_alias_score(src, tgt)
            raw   = (sem * _W_SEMANTIC + typ * _W_TYPE
                     + _CONTEXT_DEFAULT * _W_CONTEXT + alias * _W_ALIAS)
            final = apply_hard_guards(raw, typ)

            candidates.append(MappingCandidate(
                source_field=src,
                target_slot=tgt,
                semantic_score=sem,
                type_score=typ,
                combined_score=final,
            ))

    # 단계 7: 슬롯 제약 최적화
    return resolve_slot_assignments(candidates, target_slots)
