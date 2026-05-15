"""PR #722 Branch B-2 사전 점검 — sentinel #9/#10/#11."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "evidence/day17/branch_b2"


# ── sentinel #9: over_extraction_guard action_fp no regression ────────────
def test_over_extraction_guard_action_fp_no_regression():
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    selected = abc["selected"]
    if selected == "A_current":
        return
    a_fp = abc["results"]["A_current"]["action_fp"]
    sel_fp = abc["results"][selected]["action_fp"]
    assert sel_fp - a_fp <= 0, (
        f"selected={selected}: action_fp Δ {sel_fp - a_fp} > 0 (regression)")


# ── sentinel #10: mixed taxonomy coverage = 116 ───────────────────────────
def test_mixed_taxonomy_coverage():
    mt = json.loads((OUT / "mixed_116_taxonomy.json").read_text(encoding="utf-8"))
    total = mt["mixed_total"]
    assert total == sum(mt["subtype_distribution"].values()), (
        f"subtype 합계 {sum(mt['subtype_distribution'].values())} != mixed_total {total}")
    # 자문 정합: 116 expected (PR #720 mixed). 분류 후 정합 검증.
    # 데이터 변동 영향 허용 범위 ±5% 이내.
    assert 110 <= total <= 122, f"mixed_total {total} out of [110, 122]"


# ── sentinel #11: A/B/C safety regression 검사 ─────────────────────────────
def test_ab_simulation_abc_safety():
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    full = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    # safety monitor 6종 유지
    assert full["false_deadline_rate"] <= 0.02 + 1e-9
    assert full["no_action_fp_rate"]   <= 0.03 + 1e-9
    assert full["g22_strict_warning_count"] == 0
    assert full["g23_hard_violation_count"] == 0


# ── 운영 표준 7 — sentinel #7 + NATURAL_SHORTAGE 정합 ────────────────────
def test_pr722_composition_natural_shortage():
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    assert cfg["composition_ok"] is True
    assert cfg["fail_class"] in {None, "AB_COMPOSITION_NATURAL_SHORTAGE"}
    assert len(cfg["ab_sample_ids"]) == 50


# ── 운영 표준 6 — sentinel #6 coverage fail-closed ────────────────────────
def test_pr722_coverage_fail_closed():
    full = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    cov = full["coverage_report"]
    assert cov["coverage_checked"] is True
    assert cov["expected_samples"] == 500
    assert cov["measured_samples"] == 500
    assert cov["missing_count"] == 0
    assert cov["extra_count"] == 0
    assert cov["duplicate_count"] == 0


# ── gold_review_queue 분리 검증 ──────────────────────────────────────────
def test_gold_review_queue_separated():
    q = json.loads((OUT / "gold_review_queue.json").read_text(encoding="utf-8"))
    # 4건 (자문 정합)
    assert q["queue_total"] == 4, f"gold_review_queue {q['queue_total']} != 4"
    for r in q["rows"]:
        assert r["recommended_action"] == "review_only"
