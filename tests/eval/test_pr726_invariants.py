"""PR #726 Branch B-3B arbitration apply sentinel — #19/#20/#21."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "evidence/day20/branch_b3b_arbitration_apply"


# ── sentinel #19: selected AR rule application logic ─────────────────────
def test_selected_ar_rule_application_logic():
    """선택 AR rule 이 ar_candidate_comparison + selected design 정합."""
    fe = json.loads((OUT / "full_eval_500_12_measurement.json").read_text(encoding="utf-8"))
    breakdown = json.loads((OUT / "mixed_a_recovery_breakdown.json").read_text(encoding="utf-8"))
    # recovery_total = a1 + a3
    assert breakdown["recover_total"] == (
        breakdown["mixed_a1_recover"] + breakdown["mixed_a3_recover"])
    # f1 delta 가 음수가 아님 (회귀 없음)
    assert fe["normalized_action_f1_delta"] >= 0.0


# ── sentinel #20: MIXED-A1 recovery count within estimate ────────────────
def test_mixed_a1_recovery_count_within_estimate():
    """MIXED-A1 recovery count 가 0 ~ MIXED-A1 total 범위."""
    breakdown = json.loads((OUT / "mixed_a_recovery_breakdown.json").read_text(encoding="utf-8"))
    assert 0 <= breakdown["mixed_a1_recover"] <= breakdown["mixed_a_total"]
    assert 0 <= breakdown["mixed_a3_recover"] <= breakdown["mixed_a_total"]
    assert 0.0 <= breakdown["recovery_rate"] <= 1.0


# ── sentinel #21: Branch B-2 / D no regression after B-3B ────────────────
def test_branch_b2_d_no_regression_after_b3b():
    """Branch B-2 (action_fp) / D (deadline_f1) 회귀 없음."""
    rep = json.loads((OUT / "branch_b2_d_regression_report.json").read_text(encoding="utf-8"))
    assert rep["action_fp_regression"] is False, (
        f"Branch B-2 action_fp 회귀: {rep['branch_b3b_action_fp']} > 234")
    assert rep["deadline_f1_regression"] is False, (
        f"Branch D deadline_f1 회귀: {rep['branch_b3b_deadline_f1']} < 0.8438")
    assert rep["branch_b3b_action_fp"] <= 234
    assert rep["branch_b3b_deadline_f1"] >= 0.8438 - 1e-9


# ── coverage fail-closed (sentinel #6, 12 필드) ──────────────────────────
def test_pr726_coverage_12_fields():
    cov = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    for fld in ["coverage_checked", "expected_samples", "measured_samples",
                "missing_count", "missing_ids", "extra_count", "extra_ids",
                "gold_duplicate_count", "gold_duplicate_ids",
                "prediction_duplicate_count", "prediction_duplicate_ids",
                "fail_class"]:
        assert fld in cov, f"missing coverage field {fld}"
    assert cov["expected_samples"] == 500
    assert cov["fail_class"] is None


# ── Standard 11: AB variant distinctness ─────────────────────────────────
def test_pr726_ab_variant_distinct():
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    # B 와 C 가 distinct measurement (Standard 11)
    assert abc["variant_distinct"] is True or \
           abc["results"]["B_ar2"]["f1"] != abc["results"]["C_ar2_ar4"]["f1"]


# ── safety monitor ───────────────────────────────────────────────────────
def test_pr726_safety_monitor():
    fe = json.loads((OUT / "full_eval_500_12_measurement.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"] <= 0.03 + 1e-9
    assert fe["g22_strict_warning_count"] == 0
    assert fe["g23_hard_violation_count"] == 0
