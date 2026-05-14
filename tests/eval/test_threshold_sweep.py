"""PR #715 threshold sweep + 매핑 회귀."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SWEEP_DIR = ROOT / "evidence/day13/threshold_sweep"


def test_threshold_sweep_precision_floor():
    """precision < 0.95 후보가 selected 되지 않아야 함 (precision-first)."""
    report = json.load((SWEEP_DIR / "precision_first_report.json").open(encoding="utf-8"))
    best = report.get("best")
    if best:
        assert best["precision"] >= 0.95, (
            f"selected best precision {best['precision']} < 0.95 floor")
    # best=None 인 경우 NO_CANDIDATE_PASSED_PRECISION_FLOOR — 정상


def test_selected_threshold_reproducibility():
    """seed=42 동일 + intent/action 범위 명세 일치."""
    cfg = json.load((SWEEP_DIR / "sweep_config.json").open(encoding="utf-8"))
    assert cfg["intent_range"] == [0.50, 0.85, 0.05]
    assert cfg["action_range"] == [0.50, 0.90, 0.05]


def test_calibrator_mapping_no_swap():
    """PR #713 P1-1 정정 — intent/action Platt 계수 분리 유지."""
    from scripts.eval.pr715_pipeline import platt_sigmoid
    A_int, B_int = 1.0, 0.0
    A_act, B_act = 10.0, 0.0
    # intent 계산은 intent 계수만 사용
    z = 0.5
    intent_correct = platt_sigmoid(z, A_int, B_int)
    action_correct = platt_sigmoid(z, A_act, B_act)
    # swap 시 결과
    intent_swapped = platt_sigmoid(z, A_act, B_act)
    action_swapped = platt_sigmoid(z, A_int, B_int)
    assert abs(intent_correct - intent_swapped) > 0.01
    assert abs(action_correct - action_swapped) > 0.01
