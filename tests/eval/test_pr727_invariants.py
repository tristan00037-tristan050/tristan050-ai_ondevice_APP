"""PR #727 Branch D-2 targeted deadline sentinel — #25/#26/#27/#28."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day21/branch_d2_targeted_deadline"

from scripts.eval.pr727_branch_d2_targeted_deadline import (  # noqa
    d2_classify, measure_deadline,
)


# ── sentinel #25: D2-A HARD strength enforcement ─────────────────────────
def test_d2a_hard_strength_enforcement():
    assert d2_classify("내일까지 보고서 제출", "SOFT")[0] == "HARD"
    assert d2_classify("금요일까지 회신", "SOFT")[0] == "HARD"
    assert d2_classify("오전 10시까지 전달", "NONE")[0] == "HARD"
    # actionable=true
    assert d2_classify("내일까지 제출", "SOFT")[1] is True


# ── sentinel #26: D2-B SOFT relative time ────────────────────────────────
def test_d2b_soft_relative_time_normalization():
    assert d2_classify("오늘 중 처리", "HARD")[0] == "SOFT"
    assert d2_classify("이번 주 안에 검토", "HARD")[0] == "SOFT"
    assert d2_classify("가능하면 공유", "NONE")[0] == "SOFT"


# ── sentinel #27: D2-C/D/E non-actionable 보존 ───────────────────────────
def test_d2c_d2d_d2e_non_actionable_preservation():
    # D2-C INQUIRY
    t, act = d2_classify("마감이 언제까지인가요", "HARD")
    assert t == "INQUIRY" and act is False
    # D2-D CONDITION
    t, act = d2_classify("검토가 완료되면 알려주세요", "SOFT")
    assert t == "CONDITION" and act is False
    # D2-E URGENCY
    t, act = d2_classify("지금 바로 처리", "HARD")
    assert t == "URGENCY" and act is False


# ── sentinel #28: Branch D-1/D-3/D-4 no regression ───────────────────────
def test_branch_d1_d3_d4_no_regression_after_d2():
    rep = json.loads((OUT / "branch_d1_d3_d4_regression_report.json").read_text(encoding="utf-8"))
    assert rep["deadline_f1_regression"] is False, (
        f"deadline_f1 회귀: {rep['d2_deadline_f1']} < 0.8438")
    assert rep["none_act_regression"] is False, (
        f"NONE→actionable 회귀: {rep['d2_none_act']} > 2")
    assert rep["d2_deadline_f1"] >= 0.8438 - 1e-9


# ── Branch B-2 회귀 monitor ──────────────────────────────────────────────
def test_pr727_branch_b2_no_regression():
    rep = json.loads((OUT / "branch_b2_regression_report.json").read_text(encoding="utf-8"))
    assert rep["action_fp_regression"] is False
    assert rep["d2_action_fp"] <= 234


# ── coverage 12 필드 (Standard 9) ────────────────────────────────────────
def test_pr727_coverage_12_fields():
    cov = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    for fld in ["coverage_checked", "expected_samples", "measured_samples",
                "missing_count", "missing_ids", "extra_count", "extra_ids",
                "gold_duplicate_count", "gold_duplicate_ids",
                "prediction_duplicate_count", "prediction_duplicate_ids",
                "fail_class"]:
        assert fld in cov
    assert cov["expected_samples"] == 500
    assert cov["fail_class"] is None


# ── Standard 11 variant distinctness (metric-only) ───────────────────────
def test_pr727_ab_variant_distinct_metric_only():
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    b = abc["results"]["B_d1"]
    c = abc["results"]["C_d1_d2"]
    keys = ["deadline_tp", "deadline_fp", "deadline_fn", "deadline_f1"]
    expected = any(b.get(k) != c.get(k) for k in keys)
    assert abc["variant_distinct"] == expected
    assert abc["variant_distinct_basis"].startswith("metric-only")


# ── safety monitor ───────────────────────────────────────────────────────
def test_pr727_safety_monitor():
    fe = json.loads((OUT / "full_eval_500_13_measurement.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"] <= 0.03 + 1e-9
    assert fe["g22_strict_warning_count"] == 0
    assert fe["g23_hard_violation_count"] == 0


# ── deadline_f1 외부 베타 기준 측정 ──────────────────────────────────────
def test_pr727_deadline_f1_measurement():
    fe = json.loads((OUT / "full_eval_500_13_measurement.json").read_text(encoding="utf-8"))
    assert fe["deadline_f1_after"] >= fe["deadline_f1_before"], "deadline_f1 회귀"
    # delta 양수
    assert fe["deadline_f1_delta"] >= 0.0


# ── sentinel #29: false_deadline_rate 는 D-2 patched actionable 기준 ──────
def test_false_deadline_rate_uses_d2_actionable():
    """Codex P1: pre-patch actionable=True 라도 D2-C INQUIRY 보정 시
    non-actionable 로 흡수 → false_deadline 미집계."""
    # gold NONE + pre-patch deadline_is_actionable=True + D2-C "언제까지" 패턴
    items = [{"sample_id": "T1", "text": "마감이 언제까지인가요",
              "deadline_type": "NONE"}]
    preds = [{"sample_id": "T1",
              "pred": {"deadline_type": "HARD", "deadline_is_actionable": True}}]
    d2 = measure_deadline(items, preds, "d2_targeted")
    # D2-C 가 INQUIRY + actionable=False 로 변환 → false_deadline 미집계
    assert d2["false_deadline_count"] == 0
    assert d2["false_deadline_rate"] == 0.0
    assert d2["computed_from_d2_actionable"] is True
    # 동일 fixture 가 baseline mode 에서는 pre-patch actionable=True → 집계
    base = measure_deadline(items, preds, "baseline_d1")
    assert base["false_deadline_count"] == 1
    # evidence 정합: d2_targeted mode 명시
    fe = json.loads((OUT / "full_eval_500_13_measurement.json").read_text(encoding="utf-8"))
    assert fe["computed_from_d2_actionable"] is True
    assert fe["false_deadline_mode"] == "d2_targeted"


# ── sentinel #30: baseline mode 는 pre-patch actionable 사용 ─────────────
def test_baseline_mode_uses_pre_patch_actionable():
    """baseline_d1 mode 는 pre-patch deadline_is_actionable 사용 + mode 명시."""
    items = [{"sample_id": "T1", "text": "회의록 정리해 주세요",
              "deadline_type": "NONE"}]
    preds = [{"sample_id": "T1",
              "pred": {"deadline_type": "NONE", "deadline_is_actionable": True}}]
    base = measure_deadline(items, preds, "baseline_d1")
    assert base["mode"] == "baseline_d1"
    assert base["computed_from_d2_actionable"] is False
    # pre-patch actionable=True + gold NONE → false_deadline 집계
    assert base["false_deadline_count"] == 1
    # unknown mode 는 fail-closed
    try:
        measure_deadline(items, preds, "proceed_mode")
        raise AssertionError("unknown mode 가 ValueError 미발생")
    except ValueError:
        pass
