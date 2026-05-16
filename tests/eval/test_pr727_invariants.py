"""PR #727 Branch D-2 targeted deadline sentinel — #25/#26/#27/#28."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day21/branch_d2_targeted_deadline"

from scripts.eval.pr727_branch_d2_targeted_deadline import d2_classify  # noqa


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
