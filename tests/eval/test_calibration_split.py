"""PR #715 calibration split 회귀 (Hard Gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SPLIT_DIR = ROOT / "evidence/day13/calibration_split"


def _load_ids(name):
    return set(json.load((SPLIT_DIR / name).open(encoding="utf-8"))["ids"])


def test_calibration_split_disjoint():
    fit = _load_ids("calibration_fit_set_ids.json")
    hold = _load_ids("final_eval_holdout_ids.json")
    assert fit.isdisjoint(hold), "fit ∩ holdout = ∅ 위반 (data leakage)"


def test_calibration_split_size():
    fit = _load_ids("calibration_fit_set_ids.json")
    hold = _load_ids("final_eval_holdout_ids.json")
    assert len(fit) == 150
    assert len(hold) == 350


def test_stratification_sanity():
    """auto_apply true 가 양쪽 모두에 분포되어야 함 (절대 0 금지)."""
    audit = json.load((SPLIT_DIR / "split_audit.json").open(encoding="utf-8"))
    assert audit["fit_dist"]["auto_apply_true"] >= 1
    assert audit["holdout_dist"]["auto_apply_true"] >= 1
    # 알고리즘 팀 §1 — fit >= 8, holdout >= 18
    assert audit["fit_dist"]["auto_apply_true"] >= 8
    assert audit["holdout_dist"]["auto_apply_true"] >= 18


def test_no_full_dataset_fit():
    """fit 크기 500 이면 fail."""
    fit = _load_ids("calibration_fit_set_ids.json")
    assert len(fit) != 500, "FULL_DATASET_FIT_FORBIDDEN"
    assert len(fit) < 500
