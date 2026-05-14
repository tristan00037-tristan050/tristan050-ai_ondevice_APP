"""Codex P1-1 calibration 매핑 회귀 (옵션 A): intent→intent, action→action."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.run_card1_six_five_six import _apply_calibration, _platt_sigmoid


def _make_calibrator(intent_A, intent_B, action_A, action_B):
    return {"targets": {"intent": {"A": intent_A, "B": intent_B},
                        "action": {"A": action_A, "B": action_B}}}


def test_calibration_uses_matching_intent_coefficients():
    """intent_confidence_calibrated 는 intent 계수 (A,B) 만 적용해야 함."""
    cal = _make_calibrator(intent_A=1.0, intent_B=0.0,
                           action_A=10.0, action_B=0.0)
    pred = {"raw_intent_confidence": 0.5, "raw_action_confidence": 0.0}
    _apply_calibration(pred, cal)
    expected = _platt_sigmoid(0.5, 1.0, 0.0)
    assert abs(pred["intent_confidence_calibrated"] - expected) < 1e-9


def test_calibration_uses_matching_action_coefficients():
    """action_confidence_calibrated 는 action 계수 (A,B) 만 적용해야 함."""
    cal = _make_calibrator(intent_A=1.0, intent_B=0.0,
                           action_A=10.0, action_B=0.0)
    pred = {"raw_intent_confidence": 0.0, "raw_action_confidence": 0.5}
    _apply_calibration(pred, cal)
    expected = _platt_sigmoid(0.5, 10.0, 0.0)
    assert abs(pred["action_confidence_calibrated"] - expected) < 1e-9


def test_calibration_does_not_swap_intent_action_params():
    """매우 다른 intent / action 계수에서 swap 시 결과가 명확히 달라야 함."""
    cal = _make_calibrator(intent_A=1.0, intent_B=0.0,
                           action_A=10.0, action_B=0.0)
    pred = {"raw_intent_confidence": 0.5, "raw_action_confidence": 0.5}
    _apply_calibration(pred, cal)
    intent_correct = _platt_sigmoid(0.5, 1.0, 0.0)
    action_correct = _platt_sigmoid(0.5, 10.0, 0.0)
    # swap (이전 버그) 시 결과
    intent_swapped = _platt_sigmoid(0.5, 10.0, 0.0)
    action_swapped = _platt_sigmoid(0.5, 1.0, 0.0)
    assert abs(pred["intent_confidence_calibrated"] - intent_correct) < 1e-9
    assert abs(pred["action_confidence_calibrated"] - action_correct) < 1e-9
    # swap 결과와는 명확히 달라야 함
    assert abs(pred["intent_confidence_calibrated"] - intent_swapped) > 0.01
    assert abs(pred["action_confidence_calibrated"] - action_swapped) > 0.01
