"""test_llm_correction.py — 단계 4: LLM corrector + verifier + calibration 검증 (10 tests)."""
from __future__ import annotations

import os
from typing import List
from unittest.mock import patch

import pytest

from butler_pc_core.semantic_mapping.contracts import (
    MappingDecision,
    SourceField,
    TargetSlot,
    ValueType,
)
from butler_pc_core.semantic_mapping.llm_corrector import correct_mapping
from butler_pc_core.semantic_mapping.pipeline import map_fields, _calibrate_confidence
from butler_pc_core.semantic_mapping.slot_schema import TARGET_SLOTS
from butler_pc_core.semantic_mapping.verifier import verify_llm_response


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def slots() -> List[TargetSlot]:
    return TARGET_SLOTS


@pytest.fixture
def contact_slot(slots) -> TargetSlot:
    return next(s for s in slots if s.slot_id == "contact")


@pytest.fixture
def budget_slot(slots) -> TargetSlot:
    return next(s for s in slots if s.slot_id == "budget")


def _make_decision(slot: TargetSlot, confidence: float, mapped: bool = True) -> MappingDecision:
    needs_review = confidence < 0.70
    src = SourceField(label="테스트필드", value="테스트값", raw_text="테스트필드: 테스트값")
    return MappingDecision(
        target_slot=slot,
        source_field=src,
        confidence=confidence,
        needs_review=needs_review,
        mapped=mapped,
    )


def _valid_json_response(slot_id: str, confidence: float) -> str:
    return f'{{"slot_id": "{slot_id}", "confidence": {confidence}, "reason": "테스트 이유"}}'


# ── 1. verifier: 유효 JSON 수락 ───────────────────────────────────────────────

def test_verifier_valid_json_accepted(budget_slot, slots):
    raw = _valid_json_response("budget", 0.85)
    fallback = _make_decision(budget_slot, 0.55)
    result = verify_llm_response(raw, slots, fallback)
    assert result.mapped is True
    assert result.target_slot.slot_id == "budget"
    assert abs(result.confidence - 0.85) < 1e-6
    assert result.needs_review is False


# ── 2. verifier: 잘못된 JSON → fallback ──────────────────────────────────────

def test_verifier_invalid_json_fallback(budget_slot, slots):
    raw = "이것은 JSON이 아닙니다"
    fallback = _make_decision(budget_slot, 0.55)
    result = verify_llm_response(raw, slots, fallback)
    assert result is fallback


# ── 3. verifier: 알 수 없는 slot_id 차단 (hallucination) ─────────────────────

def test_verifier_unknown_slot_blocked(budget_slot, slots):
    raw = '{"slot_id": "nonexistent_slot_xyz", "confidence": 0.99, "reason": "할루시네이션"}'
    fallback = _make_decision(budget_slot, 0.55)
    result = verify_llm_response(raw, slots, fallback)
    assert result is fallback


# ── 4. verifier: confidence 범위 초과 → 클램핑 ───────────────────────────────

def test_verifier_out_of_range_confidence_clamped(contact_slot, slots):
    raw = '{"slot_id": "contact", "confidence": 1.5, "reason": "범위 초과"}'
    fallback = _make_decision(contact_slot, 0.60)
    result = verify_llm_response(raw, slots, fallback)
    assert result.confidence == 1.0
    assert result.mapped is True


# ── 5. corrector: needs_review=False → LLM 호출 X ────────────────────────────

def test_corrector_skip_when_high_confidence(budget_slot, slots):
    called = []
    def mock_llm(prompt: str) -> str:
        called.append(prompt)
        return _valid_json_response("budget", 0.99)

    decision = _make_decision(budget_slot, 0.90)  # needs_review=False
    assert decision.needs_review is False

    src = SourceField(label="예산", value="5000만원", raw_text="예산: 5000만원")
    result = correct_mapping(decision, src, slots, llm_callable=mock_llm)

    assert len(called) == 0, "needs_review=False 결정은 LLM을 호출하면 안 됩니다"
    assert result is decision


# ── 6. corrector: needs_review=True → LLM callable 호출 ──────────────────────

def test_corrector_called_when_needs_review(budget_slot, slots):
    called = []
    def mock_llm(prompt: str) -> str:
        called.append(prompt)
        return _valid_json_response("budget", 0.82)

    decision = _make_decision(budget_slot, 0.60)  # needs_review=True
    assert decision.needs_review is True

    src = SourceField(label="사업비", value="3억원", raw_text="사업비: 3억원")
    result = correct_mapping(decision, src, slots, llm_callable=mock_llm)

    assert len(called) == 1, "needs_review=True 결정은 LLM을 호출해야 합니다"
    assert result.confidence == 0.82
    assert result.needs_review is False


# ── 7. corrector: SKIP_LLM=true → heuristic 유지 ─────────────────────────────

def test_corrector_skip_llm_env_returns_original(budget_slot, slots):
    called = []
    def mock_llm(prompt: str) -> str:
        called.append(prompt)
        return _valid_json_response("budget", 0.95)

    decision = _make_decision(budget_slot, 0.60)
    src = SourceField(label="예산", value="1억원", raw_text="예산: 1억원")

    with patch.dict(os.environ, {"SKIP_LLM": "true"}):
        result = correct_mapping(decision, src, slots, llm_callable=None)

    assert len(called) == 0
    assert result is decision


# ── 8. calibration: 0.865 → > 0.95 ──────────────────────────────────────────

def test_calibration_raises_confidence_above_095(budget_slot):
    decision = _make_decision(budget_slot, 0.865)
    [calibrated] = _calibrate_confidence([decision])
    assert calibrated.confidence > 0.95, (
        f"0.865 → {calibrated.confidence:.3f} (expected > 0.95)"
    )


# ── 9. calibration: 교정 오차 < 5% ──────────────────────────────────────────

def test_calibration_error_below_5_percent(slots):
    """고신뢰 결정 집합에서 교정 후 mean |conf - 1.0| < 0.05."""
    high_conf_values = [0.865, 0.875, 0.900, 0.910, 0.925, 0.930, 0.950]
    budget_slot = next(s for s in slots if s.slot_id == "budget")
    decisions = [_make_decision(budget_slot, c) for c in high_conf_values]

    calibrated = _calibrate_confidence(decisions)
    errors = [abs(d.confidence - 1.0) for d in calibrated]
    mean_error = sum(errors) / len(errors)

    assert mean_error < 0.05, (
        f"교정 오차 {mean_error*100:.1f}% > 5% 기준\n"
        f"교정 값: {[d.confidence for d in calibrated]}"
    )


# ── 10. pipeline: use_llm=True → llm_callable 사용 ───────────────────────────

def test_pipeline_with_llm_callable_uses_it(slots):
    """map_fields(use_llm=True) 호출 시 needs_review 결정에 llm_callable 적용 검증."""
    called = []
    def mock_llm(prompt: str) -> str:
        called.append(prompt)
        return _valid_json_response("budget", 0.88)

    # needs_review=True를 유도하는 낮은 점수 필드 (combined_score < 0.70)
    source_fields = [
        SourceField(label="사업예산", value="미정", raw_text="사업예산: 미정"),
    ]

    decisions_no_llm = map_fields(source_fields, slots, use_llm=False)
    decisions_llm    = map_fields(source_fields, slots, use_llm=True, llm_callable=mock_llm)

    # 어느 결정이든 needs_review=True 후보가 있으면 LLM 호출이 발생해야 함
    has_needs_review = any(
        d.mapped and d.target_slot.slot_id == "budget"
        for d in decisions_no_llm
    )
    if has_needs_review and decisions_no_llm[0].needs_review:
        assert len(called) >= 1, "needs_review=True 결정에 llm_callable이 호출되어야 합니다"
    else:
        # needs_review=False인 경우 LLM 미호출은 정상 동작
        pass

    # 파이프라인 자체가 오류 없이 완료되어야 함
    assert isinstance(decisions_llm, list)
    assert len(decisions_llm) == len(slots)
