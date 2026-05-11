"""slot_resolver.py — greedy 슬롯 제약 최적화 (단계 5).

one-to-many collapse 방지:
  - 1 SourceField → 1 TargetSlot (greedy 최고점 우선)
  - 1 TargetSlot → 1 SourceField (중복 배정 불가)
  - combined_score < 0.49 → unmapped
  - 0.49 ≤ combined_score < 0.70 → needs_review=True
"""
from __future__ import annotations

from typing import List

from .contracts import MappingCandidate, MappingDecision, TargetSlot

_CONFIDENCE_MIN    = 0.49
_CONFIDENCE_REVIEW = 0.70


def resolve_slot_assignments(
    candidates: List[MappingCandidate],
    target_slots: List[TargetSlot],
) -> List[MappingDecision]:
    """후보 목록에서 greedy 슬롯 배정 결정."""
    sorted_cands = sorted(candidates, key=lambda c: c.combined_score, reverse=True)

    used_sources: set[int] = set()       # id(SourceField) — 이미 배정된 소스
    best_per_slot: dict[str, MappingCandidate] = {}

    for cand in sorted_cands:
        slot_id = cand.target_slot.slot_id
        src_id  = id(cand.source_field)

        if src_id in used_sources:
            continue
        if slot_id in best_per_slot:
            continue

        best_per_slot[slot_id] = cand
        used_sources.add(src_id)

    decisions: List[MappingDecision] = []
    for slot in target_slots:
        cand = best_per_slot.get(slot.slot_id)

        if cand is None or cand.combined_score < _CONFIDENCE_MIN:
            decisions.append(MappingDecision(
                target_slot=slot,
                source_field=None,
                confidence=0.0,
                needs_review=False,
                mapped=False,
            ))
        elif cand.combined_score < _CONFIDENCE_REVIEW:
            decisions.append(MappingDecision(
                target_slot=slot,
                source_field=cand.source_field,
                confidence=round(cand.combined_score, 3),
                needs_review=True,
                mapped=True,
            ))
        else:
            decisions.append(MappingDecision(
                target_slot=slot,
                source_field=cand.source_field,
                confidence=round(cand.combined_score, 3),
                needs_review=False,
                mapped=True,
            ))

    return decisions
