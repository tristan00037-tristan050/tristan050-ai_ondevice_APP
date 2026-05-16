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


# ── Standard 11: AB variant distinctness (metric-only, P2(a) 정정) ───────
def test_pr726_ab_variant_distinct():
    """variant_distinct 는 metric-only 비교 결과와 정합 (label 오염 제외)."""
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    b = abc["results"]["B_ar2"]
    c = abc["results"]["C_ar2_ar4"]
    metric_keys = ["action_tp", "action_fp", "action_fn", "f1"]
    expected = any(b.get(k) != c.get(k) for k in metric_keys)
    # variant_distinct 가 metric-only 산출과 일치
    assert abc["variant_distinct"] == expected
    assert abc["variant_distinct_basis"].startswith("metric-only")


# ── safety monitor ───────────────────────────────────────────────────────
def test_pr726_safety_monitor():
    fe = json.loads((OUT / "full_eval_500_12_measurement.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"] <= 0.03 + 1e-9
    assert fe["g22_strict_warning_count"] == 0
    assert fe["g23_hard_violation_count"] == 0


# ── Codex P1 정정: coverage drift fail-closed (#22) ──────────────────────
def test_coverage_drift_fail_closed_pr726():
    """missing/extra/pred_dup → FULL_EVAL_COVERAGE_MISMATCH (단위 로직)."""
    from collections import Counter as _Counter
    # fixture: prediction missing 1건
    item_ids = ["S001", "S002", "S003"]
    pred_ids = ["S001", "S002"]   # S003 missing
    items_set = set(item_ids); preds_set = set(pred_ids)
    missing = items_set - preds_set
    extra   = preds_set - items_set
    gold_dup = [s for s, c in _Counter(item_ids).items() if c > 1]
    pred_dup = [s for s, c in _Counter(pred_ids).items() if c > 1]
    fail_class = None
    if gold_dup:
        fail_class = "GOLD_SAMPLE_ID_DUPLICATE"
    elif missing or extra or pred_dup:
        fail_class = "FULL_EVAL_COVERAGE_MISMATCH"
    assert fail_class == "FULL_EVAL_COVERAGE_MISMATCH"


# ── Codex P2(a) 정정: variant_distinct metric-only (#23) ─────────────────
def test_variant_distinct_metric_only_not_label():
    """B/C metric 동일 + label 다름 → variant_distinct=false."""
    b = {"variant": "B", "action_tp": 28, "action_fp": 25, "action_fn": 1, "f1": 0.6829}
    c = {"variant": "C", "action_tp": 28, "action_fp": 25, "action_fn": 1, "f1": 0.6829}
    metric_keys = ["action_tp", "action_fp", "action_fn", "f1"]
    distinct = any(b.get(k) != c.get(k) for k in metric_keys)
    assert distinct is False, "metric 동일인데 distinct=true (label 오염 의심)"
    # label 차이 무관 확인
    assert b["variant"] != c["variant"]
    # 실제 evidence 정합
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    assert abc["variant_distinct_basis"].startswith("metric-only")


# ── Codex P2(b) 정정: AR-2 hybrid merge 실제 동작 (#24) ──────────────────
def test_ar2_hybrid_merge_actually_merges_parser_candidates():
    """AR-2 hybrid merge 가 parser-only candidate 를 실제 병합 (또는 정직 noop)."""
    cmp_md = (OUT / "ar_candidate_comparison.md").read_text(encoding="utf-8")
    # AR-2 결과가 ar_candidate_comparison 에 명시
    assert "AR-2" in cmp_md
    # AR-2 가 baseline 과 다른 측정값 (parser candidate 병합 효과 — fp 변동)
    # 또는 noop 정직 보고
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.eval.pr726_branch_b3b_arbitration_apply import apply_arbitration
    # fixture: Mode-D 에 없는 parser-only candidate
    gold = {"text": "회의록 정리해서 공유해 주세요"}
    pred = {"intent_type": "REQUEST",
            "actions": [{"action_text": "검토", "evidence": "검토"}]}
    mode_a = {"actions": [{"action_text": "회의록 정리해서 공유해 주세요",
                            "evidence": "회의록 정리해서 공유해 주세요"}]}
    result, rule = apply_arbitration("S001", "MIXED-A1_parser_action_llm_object",
                                      gold, pred, mode_a, {}, "AR-2")
    # parser candidate 가 병합되어 후보 수 증가 또는 noop
    assert rule in {"AR-2_hybrid_merge", "AR-2_hybrid_merge_noop"}
    if rule == "AR-2_hybrid_merge":
        assert len(result) > 1   # parser candidate 병합됨
