"""test_accuracy_gate.py — 알고리즘 팀 §7-2 정확도 게이트 단위 검증 (단계 6.2).

단계 6.2: 게이트 로직 단위 영역 (합성 EvalReport 사용).
단계 6.3: 실제 65건 run_card1_evaluation() 실행 + 통과 여부 확인.

게이트 기준 (영역 완화 X):
  intent_type_accuracy         >= 90%
  deadline_extraction_f1       >= 92%
  material_extraction_f1       >= 90%
  action_extraction_f1         >= 90%
  false_deadline_rate          <= 2%
  no_action_false_positive     <= 3%
  confidence_calibration_error <= 10%
"""
from __future__ import annotations

import pytest

from butler_pc_core.card1_extraction.evaluator import (
    GATE_ACTION_F1,
    GATE_CONFIDENCE_CALIBRATION,
    GATE_DEADLINE_F1,
    GATE_FALSE_DEADLINE_RATE,
    GATE_INTENT_TYPE_ACCURACY,
    GATE_MATERIAL_F1,
    GATE_NO_ACTION_FALSE_POSITIVE,
    EvalReport,
    check_gates,
)


# ── 합성 EvalReport 생성 헬퍼 ────────────────────────────────────────────────

def _report(**overrides) -> EvalReport:
    """모든 메트릭이 완벽(1.0/0.0)인 합성 EvalReport 생성 후 override 적용."""
    defaults: dict = dict(
        total_items                  = 10,
        intent_type_accuracy         = 1.0,
        sentence_type_accuracy       = 1.0,
        deadline_precision           = 1.0,
        deadline_recall              = 1.0,
        deadline_extraction_f1       = 1.0,
        material_precision           = 1.0,
        material_recall              = 1.0,
        material_extraction_f1       = 1.0,
        action_precision             = 1.0,
        action_recall                = 1.0,
        action_extraction_f1         = 1.0,
        false_deadline_rate          = 0.0,
        no_action_false_positive     = 0.0,
        confidence_calibration_error = 0.0,
    )
    defaults.update(overrides)
    return EvalReport(**defaults)


# ── 1: intent_type_accuracy 게이트 ───────────────────────────────────────────

def test_intent_type_accuracy_gate():
    """임계값(90%)에서 PASS, 미달(-1%)에서 FAIL + 메타 검증."""
    gates_pass = check_gates(_report(intent_type_accuracy=GATE_INTENT_TYPE_ACCURACY))
    assert gates_pass["intent_type_accuracy"]["passed"], (
        f"intent_type_accuracy={GATE_INTENT_TYPE_ACCURACY:.0%} 는 게이트 통과해야 함"
    )

    gates_fail = check_gates(_report(intent_type_accuracy=GATE_INTENT_TYPE_ACCURACY - 0.01))
    g = gates_fail["intent_type_accuracy"]
    assert not g["passed"], "임계값 미달 시 게이트 실패해야 함"
    assert g["operator"]  == ">="
    assert g["threshold"] == GATE_INTENT_TYPE_ACCURACY
    assert g["value"]      < GATE_INTENT_TYPE_ACCURACY


# ── 2: deadline_extraction_f1 게이트 ─────────────────────────────────────────

def test_deadline_extraction_f1_gate():
    """임계값(92%)에서 PASS, 미달(-1%)에서 FAIL."""
    gates_pass = check_gates(_report(deadline_extraction_f1=GATE_DEADLINE_F1))
    assert gates_pass["deadline_extraction_f1"]["passed"], (
        f"deadline_extraction_f1={GATE_DEADLINE_F1:.0%} 는 게이트 통과해야 함"
    )

    gates_fail = check_gates(_report(deadline_extraction_f1=GATE_DEADLINE_F1 - 0.01))
    g = gates_fail["deadline_extraction_f1"]
    assert not g["passed"]
    assert g["operator"]  == ">="
    assert g["threshold"] == GATE_DEADLINE_F1
    assert g["value"]      < GATE_DEADLINE_F1


# ── 3: material_extraction_f1 게이트 ─────────────────────────────────────────

def test_material_extraction_f1_gate():
    """임계값(90%)에서 PASS, 미달(-1%)에서 FAIL."""
    gates_pass = check_gates(_report(material_extraction_f1=GATE_MATERIAL_F1))
    assert gates_pass["material_extraction_f1"]["passed"]

    gates_fail = check_gates(_report(material_extraction_f1=GATE_MATERIAL_F1 - 0.01))
    g = gates_fail["material_extraction_f1"]
    assert not g["passed"]
    assert g["operator"]  == ">="
    assert g["threshold"] == GATE_MATERIAL_F1


# ── 4: action_extraction_f1 게이트 ───────────────────────────────────────────

def test_action_extraction_f1_gate():
    """임계값(90%)에서 PASS, 미달(-1%)에서 FAIL."""
    gates_pass = check_gates(_report(action_extraction_f1=GATE_ACTION_F1))
    assert gates_pass["action_extraction_f1"]["passed"]

    gates_fail = check_gates(_report(action_extraction_f1=GATE_ACTION_F1 - 0.01))
    g = gates_fail["action_extraction_f1"]
    assert not g["passed"]
    assert g["operator"]  == ">="
    assert g["threshold"] == GATE_ACTION_F1


# ── 5: false_deadline_rate 게이트 ────────────────────────────────────────────

def test_false_deadline_rate_gate():
    """임계값(2%)에서 PASS (<= 기준), 초과(+1%)에서 FAIL."""
    gates_pass = check_gates(_report(false_deadline_rate=GATE_FALSE_DEADLINE_RATE))
    assert gates_pass["false_deadline_rate"]["passed"], (
        f"false_deadline_rate={GATE_FALSE_DEADLINE_RATE:.0%} 는 게이트 통과해야 함 (<=)"
    )

    gates_fail = check_gates(_report(false_deadline_rate=GATE_FALSE_DEADLINE_RATE + 0.01))
    g = gates_fail["false_deadline_rate"]
    assert not g["passed"], "임계값 초과 시 게이트 실패해야 함"
    assert g["operator"]  == "<="
    assert g["threshold"] == GATE_FALSE_DEADLINE_RATE
    assert g["value"]      > GATE_FALSE_DEADLINE_RATE


# ── 6: no_action_false_positive 게이트 ───────────────────────────────────────

def test_no_action_false_positive_gate():
    """임계값(3%)에서 PASS (<= 기준), 초과(+1%)에서 FAIL."""
    gates_pass = check_gates(_report(no_action_false_positive=GATE_NO_ACTION_FALSE_POSITIVE))
    assert gates_pass["no_action_false_positive"]["passed"]

    gates_fail = check_gates(_report(no_action_false_positive=GATE_NO_ACTION_FALSE_POSITIVE + 0.01))
    g = gates_fail["no_action_false_positive"]
    assert not g["passed"]
    assert g["operator"]  == "<="
    assert g["threshold"] == GATE_NO_ACTION_FALSE_POSITIVE
    assert g["value"]      > GATE_NO_ACTION_FALSE_POSITIVE


# ── 7: confidence_calibration_error 게이트 ───────────────────────────────────

def test_confidence_calibration_error_gate():
    """임계값(10%)에서 PASS (<= 기준), 초과(+1%)에서 FAIL."""
    gates_pass = check_gates(_report(confidence_calibration_error=GATE_CONFIDENCE_CALIBRATION))
    assert gates_pass["confidence_calibration_error"]["passed"]

    gates_fail = check_gates(_report(confidence_calibration_error=GATE_CONFIDENCE_CALIBRATION + 0.01))
    g = gates_fail["confidence_calibration_error"]
    assert not g["passed"]
    assert g["operator"]  == "<="
    assert g["threshold"] == GATE_CONFIDENCE_CALIBRATION
    assert g["value"]      > GATE_CONFIDENCE_CALIBRATION
