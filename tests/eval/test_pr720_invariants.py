"""PR #720 Branch B 사전 점검 — 운영 표준 7건 정합 + 신규 4건."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "evidence/day16/prompt_schema_patch"


def test_atomic_action_schema_valid():
    """schema_patch.json — required field 변경 없음 (optional 만 추가)."""
    sp = json.loads((OUT / "schema_patch.json").read_text(encoding="utf-8"))
    required = sp["actions_required_fields"]
    assert "action_text" in required
    assert "normalized_action" in required
    assert "source_evidence" in required
    optional = sp["actions_optional_fields"]
    for f in ["object", "recipient", "depends_on", "is_atomic"]:
        assert f in optional


def test_evidence_field_required_on_auto_apply():
    """schema_patch atomic_action_rule — evidence_substring_of_source=True."""
    sp = json.loads((OUT / "schema_patch.json").read_text(encoding="utf-8"))
    rule = sp["atomic_action_rule"]
    assert rule["evidence_substring_of_source"] is True
    assert rule["is_atomic"] is True


def test_multi_action_decomposition_no_over_extraction():
    """priority_score_report — over_extraction_risk 음수 가중치 적용."""
    pr = json.loads((OUT / "priority_score_report.json").read_text(encoding="utf-8"))
    formula = pr["formula"]
    assert "over_extraction" in formula
    assert "-" in formula  # negative weighting 존재


def test_safety_monitor_regression_guard():
    """full_eval — safety threshold 유지 (false_deadline_rate / no_action_fp_rate)."""
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"]   <= 0.03 + 1e-9
    assert fe["g23_hard_violation_count"] == 0
    assert fe["g22_strict_warning_count"] == 0


# ── sentinel #6 — coverage fail-closed (Branch B 적용) ────────────────────
def test_full_eval_coverage_fail_closed_pr720():
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    cov = fe["coverage_report"]
    assert cov["coverage_checked"] is True
    assert cov["expected_samples"] == 500
    assert cov["measured_samples"] == 500
    assert cov["missing_count"]   == 0
    assert cov["extra_count"]     == 0
    assert cov["duplicate_count"] == 0


# ── sentinel #7 — composition declared = actual (or fail_class) ───────────
def test_ab_composition_enforced_pr720():
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    declared = cfg["declared_composition"]
    actual   = cfg["actual_composition"]
    if cfg["composition_ok"]:
        for k in declared:
            assert actual[k] == declared[k]
        assert cfg["fail_class"] is None
    else:
        # 데이터셋 자연 부족 인정 — fail_class 명시 필수
        assert cfg["fail_class"] == "AB_COMPOSITION_MISMATCH"
    assert len(cfg["ab_sample_ids"]) == 50
