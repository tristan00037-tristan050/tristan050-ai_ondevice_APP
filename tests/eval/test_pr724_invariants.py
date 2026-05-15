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
