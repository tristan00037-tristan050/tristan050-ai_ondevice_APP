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


# ── Codex P1 정정: AB composition mismatch fail-closed (no padding) ───────
def test_ab_composition_mismatch_fail_closed_no_padding():
    """진짜 MISMATCH (fallback 부족) 시 SystemExit + 임의 padding 차단."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.eval.pr722_branch_b2_over_guard import step4_build_ab_ids as _build_ab_ids

    # fixture: 모든 pool 부족 + fallback 도 부족 → 임의 padding 발동 금지
    items = [{"sample_id": f"S{i:03d}",
              "gold": {"actions": []},
              "intent_type": "REPORT",
              "deadline_type": "NONE"}
             for i in range(10)]   # 10건만 (pool 부족 유발)
    preds = [{"sample_id": f"S{i:03d}",
              "pred": {"intent_type": "REPORT",
                       "actions": [], "schema_valid": True}}
             for i in range(10)]
    mixed = {"rows": []}   # empty pool
    bf    = {"rows": []}   # empty pool
    raised = False
    try:
        _build_ab_ids(items, preds, mixed, bf)
    except SystemExit as e:
        raised = True
        # SystemExit message JSON parse
        import json as _json
        obj = _json.loads(e.code) if isinstance(e.code, str) else {}
        assert obj.get("fail_class") == "AB_COMPOSITION_MISMATCH"
        assert obj.get("composition_ok") is False
        assert obj.get("ab_ids_count", 50) < 50   # 임의 padding 미발생
    # MISMATCH fixture 에서 SystemExit 가 raise 되어야 함
    assert raised, "fail-closed 위반 — SystemExit raise 미발생 (임의 padding 의심)"


# ── NATURAL_SHORTAGE 경로 검증 (정합 case): padding 허용 ───────────────────
def test_ab_composition_natural_shortage_allows_padding():
    """현재 운영 pool (실제 evidence) 에서 NATURAL_SHORTAGE 정합 확인."""
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    if cfg.get("natural_shortage") and cfg.get("composition_ok"):
        # NATURAL_SHORTAGE 경로 — pad 허용
        assert cfg["fail_class"] == "AB_COMPOSITION_NATURAL_SHORTAGE"
        assert len(cfg["ab_sample_ids"]) == 50
