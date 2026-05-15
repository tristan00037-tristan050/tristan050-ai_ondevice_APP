"""PR #724 Branch D 본진입 sentinel — #12/#13/#14/#15."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day19/branch_d_classifier_patch"

from scripts.eval.pr724_branch_d_classifier_patch import (  # noqa
    classify_hard_soft, normalize_relative_time, has_deadline_marker,
    is_non_actionable_pattern, patched_deadline_classify,
)


# ── sentinel #12: HARD ↔ SOFT classifier boundary ────────────────────────
def test_hard_soft_classifier_boundary():
    assert classify_hard_soft("내일까지 보고서 제출") == "HARD"
    assert classify_hard_soft("내일 중 처리") == "SOFT"
    assert classify_hard_soft("이번 주 금요일까지 회신") == "HARD"   # override
    assert classify_hard_soft("이번 주 안에 검토") == "SOFT"
    assert classify_hard_soft("5월 10일까지 전달") == "HARD"


# ── sentinel #13: relative_time normalization schema ─────────────────────
def test_relative_time_normalization_schema():
    sch = normalize_relative_time("내일 오전까지 보내주세요")
    assert sch["relative_anchor"] == "today"
    assert sch["day_offset"] == 1
    assert sch["time_part"] == "morning"
    assert "deadline_strength" in sch
    # relative time 없으면 빈 dict
    assert normalize_relative_time("회의록 정리해 주세요") == {}


# ── sentinel #14: NONE → actionable block on no marker ───────────────────
def test_none_to_actionable_block_on_no_marker():
    # deadline marker 없는 텍스트 → HARD/SOFT pred 가 NONE 으로 보정
    assert patched_deadline_classify("회의록 정리해 주세요", "HARD") == "NONE"
    assert patched_deadline_classify("자료 공유 부탁드립니다", "SOFT") == "NONE"
    # deadline marker 있으면 보존/재분류
    result = patched_deadline_classify("내일까지 제출", "SOFT")
    assert result in {"HARD", "SOFT"}
    assert has_deadline_marker("내일까지 제출") is True
    assert has_deadline_marker("회의록 정리") is False


# ── sentinel #15: INQUIRY/URGENCY/CONDITION 보존 ─────────────────────────
def test_inquiry_urgency_condition_preserved():
    assert is_non_actionable_pattern("마감이 언제인가요") is True
    assert patched_deadline_classify("마감이 언제인가요?", "HARD") == "INQUIRY"
    assert patched_deadline_classify("지금 바로 처리", "HARD") == "URGENCY"
    assert patched_deadline_classify("검토가 완료되면 알려주세요", "SOFT") == "CONDITION"


# ── full eval coverage (sentinel #6) ─────────────────────────────────────
def test_pr724_coverage_fail_closed():
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    cov = fe["coverage_report"]
    assert cov["coverage_checked"] is True
    assert cov["expected_samples"] == 500
    assert cov["measured_samples"] == 500
    assert cov["gold_duplicate_count"] == 0
    assert cov["fail_class"] is None


# ── Branch B-2 action 회귀 monitor ───────────────────────────────────────
def test_branch_b2_action_no_regression():
    rep = json.loads((OUT / "action_safety_regression_report.json").read_text(encoding="utf-8"))
    assert rep["action_fp_regression"] is False, (
        f"action_fp 회귀: {rep['branch_d_action_fp']} > baseline 234")
    assert rep["branch_d_action_fp"] <= 234


# ── safety monitor 6종 ──────────────────────────────────────────────────
def test_pr724_safety_monitor():
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"] <= 0.03 + 1e-9
    assert fe["g22_strict_warning_count"] == 0
    assert fe["g23_hard_violation_count"] == 0


# ── Codex P1 정정: C variant distinct ────────────────────────────────────
def test_ab_simulation_c_variant_distinct_from_b():
    """C variant 가 B 와 distinct (D-2 relative time 정밀화 효과 측정)."""
    abc = json.loads((OUT / "ab_simulation_abc_results.json").read_text(encoding="utf-8"))
    r = abc["results"]
    b = r["B_d1_d3_d4"]
    c = r["C_b_plus_d2"]
    # B 와 C 가 동일 객체가 아니어야 함 (distinct 측정)
    assert (b["deadline_tp"], b["deadline_fp"], b["deadline_fn"]) != \
           (c["deadline_tp"], c["deadline_fp"], c["deadline_fn"]) or \
           b["deadline_f1"] != c["deadline_f1"], (
        "C variant 가 B 와 동일 — D-2 미구현 의심")
    # delta_table 에 B_vs_A / C_vs_A 모두 존재
    assert "B_vs_A" in abc["delta_table"]
    assert "C_vs_A" in abc["delta_table"]


# ── Codex P2 정정: AB sampler multi-category distribution ────────────────
def test_ab_sampler_multi_category_distribution():
    """artificial shortage 차단 — declared 충족 또는 NATURAL_SHORTAGE 만."""
    cfg = json.loads((OUT / "ab_eval_50_results.json").read_text(encoding="utf-8"))
    declared = cfg["declared_composition"]
    actual = cfg["actual_composition"]
    # composition_ok 인 경우: 정합 또는 NATURAL_SHORTAGE
    assert cfg["composition_ok"] is True
    assert cfg["fail_class"] in {None, "AB_COMPOSITION_NATURAL_SHORTAGE"}
    # ab_sample_ids 50건 정합
    assert len(cfg["ab_sample_ids"]) == 50


# ── Codex P2 정정: NATURAL_SHORTAGE 는 multi-category fallback 후 부족만 ──
def test_natural_shortage_warns_only_on_real_pool_exhaustion():
    """shortage_log 는 unique pool + multi-category 배정 소진 후 남은 부족.

    P2 정정: greedy global-seen 인위 부족 차단. multi-category sample 은
    shortage 카테고리 우선 배정 — 그 후에도 부족하면 NATURAL_SHORTAGE.
    available 필드는 전체 pool 크기 (정보용) — multi-category 경합으로
    available >= declared 여도 NATURAL_SHORTAGE 가능.
    """
    cfg = json.loads((OUT / "ab_eval_50_results.json").read_text(encoding="utf-8"))
    if cfg["fail_class"] == "AB_COMPOSITION_NATURAL_SHORTAGE":
        assert cfg["composition_ok"] is True
        assert len(cfg["ab_sample_ids"]) == 50
    for entry in cfg.get("shortage_log", []):
        assert entry["shortage"] > 0
        assert entry["declared"] >= entry["shortage"]
