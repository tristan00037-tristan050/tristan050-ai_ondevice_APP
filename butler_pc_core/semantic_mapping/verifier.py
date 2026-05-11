"""verifier.py — LLM 응답 JSON 검증 + 할루시네이션 차단 + 폴백 (단계 4)."""
from __future__ import annotations

import json
import re
from typing import List

from .contracts import MappingDecision, TargetSlot


def verify_llm_response(
    raw_response: str,
    candidate_slots: List[TargetSlot],
    fallback_decision: MappingDecision,
) -> MappingDecision:
    """
    LLM 응답 구조 검증 → 정정된 MappingDecision 반환.

    실패 조건 (모두 fallback 반환):
      - JSON 파싱 불가
      - slot_id 타입 오류
      - slot_id가 candidate_slots 외부 값 (할루시네이션)
      - confidence 타입 오류
    통과 시:
      - confidence 범위 [0, 1] 클램핑
      - needs_review = confidence < 0.70
    """
    try:
        m = re.search(r"\{[^{}]*\}", raw_response, re.DOTALL)
        if not m:
            return fallback_decision

        data = json.loads(m.group())

        slot_id = data.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            return fallback_decision

        # ★ 할루시네이션 차단 — 알려진 슬롯 ID만 허용
        valid_ids = {s.slot_id for s in candidate_slots}
        if slot_id not in valid_ids:
            return fallback_decision

        raw_conf = data.get("confidence", 0.5)
        if not isinstance(raw_conf, (int, float)):
            return fallback_decision

        confidence = max(0.0, min(1.0, float(raw_conf)))
        target_slot = next(s for s in candidate_slots if s.slot_id == slot_id)

        return MappingDecision(
            target_slot=target_slot,
            source_field=fallback_decision.source_field,
            confidence=round(confidence, 3),
            needs_review=confidence < 0.70,
            mapped=True,
        )

    except Exception:
        return fallback_decision
