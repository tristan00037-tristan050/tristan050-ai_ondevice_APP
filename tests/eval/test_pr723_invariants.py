"""PR #723 Branch D 측정 PR sentinel."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "evidence/day18/branch_d_measurement"


def test_pr723_coverage_fail_closed():
    d = json.loads((OUT / "deadline_f1_breakdown.json").read_text(encoding="utf-8"))
    cov = d["coverage_report"]
    assert cov["coverage_checked"] is True
    assert cov["expected_samples"] == 500
    assert cov["measured_samples"] == 500
    assert cov["missing_count"] == 0
    assert cov["extra_count"] == 0
    assert cov["gold_duplicate_count"] == 0
    assert cov["prediction_duplicate_count"] == 0


def test_deadline_f1_breakdown_consistency():
    """TP+FP+FN sum + type_match 일관성."""
    d = json.loads((OUT / "deadline_f1_breakdown.json").read_text(encoding="utf-8"))
    tp, fp, fn = d["deadline_tp"], d["deadline_fp"], d["deadline_fn"]
    assert tp >= 0 and fp >= 0 and fn >= 0
    denom = 2 * tp + fp + fn
    if denom > 0:
        expected = round(2 * tp / denom, 4)
        assert abs(d["deadline_f1"] - expected) < 1e-9, (
            f"f1 산식 불일치 ({d['deadline_f1']} vs {expected})")
    # type_distribution 합 = total_samples
    assert sum(d["type_distribution"].values()) == d["total_samples"]


def test_confusion_5종_categories_present():
    """5종 + 추가 카테고리 모두 산출."""
    c = json.loads((OUT / "inquiry_urgency_condition_confusion.json").read_text(encoding="utf-8"))
    required_keys = [
        "INQUIRY_misclassified_as_HARD_or_SOFT",
        "URGENCY_misclassified_as_SOFT",
        "URGENCY_misclassified_as_HARD_or_SOFT",
        "CONDITION_misclassified_as_HARD_or_SOFT",
        "HARD_misclassified_as_SOFT",
        "SOFT_misclassified_as_HARD",
        "NONE_misclassified_as_actionable",
    ]
    for k in required_keys:
        assert k in c, f"missing category {k}"
        assert "count" in c[k] and "gold_total" in c[k] and "rate" in c[k]


def test_relative_time_normalization_measured():
    """relative time normalization 측정 영역."""
    r = json.loads((OUT / "relative_time_normalization_errors.json").read_text(encoding="utf-8"))
    assert r["relative_time_total"] >= 0
    assert r["absolute_time_total"] >= 0
    assert 0.0 <= r["relative_time_mismatch_rate"] <= 1.0
    # mismatch_rows 는 최대 50건 (sample 상한)
    assert len(r["mismatch_rows"]) <= 50


def test_gold_duplicate_sample_id_fail_closed():
    """Codex P2 정정 — items duplicate sample_id 검출 시 fail-closed."""
    from collections import Counter as _Counter
    items = [{"sample_id": "S001"}, {"sample_id": "S001"}, {"sample_id": "S002"}]
    item_id_list = [it["sample_id"] for it in items]
    gold_duplicate_ids = [s for s, c in _Counter(item_id_list).items() if c > 1]
    assert gold_duplicate_ids == ["S001"]
    fail_class = "GOLD_SAMPLE_ID_DUPLICATE" if gold_duplicate_ids else None
    assert fail_class == "GOLD_SAMPLE_ID_DUPLICATE"


def test_coverage_report_10_fields_present():
    """coverage_report 10 필드 정합 (P2 정정 후)."""
    d = json.loads((OUT / "deadline_f1_breakdown.json").read_text(encoding="utf-8"))
    cov = d["coverage_report"]
    for fld in ["coverage_checked", "expected_samples", "measured_samples",
                "missing_count", "extra_count",
                "gold_duplicate_count", "gold_duplicate_ids",
                "prediction_duplicate_count", "prediction_duplicate_ids",
                "fail_class"]:
        assert fld in cov, f"missing coverage_report field {fld}"
    assert cov["gold_duplicate_count"] == 0
    assert cov["prediction_duplicate_count"] == 0


def test_branch_d_main_pr_readiness_quantitative():
    """Branch D 본진입 PR 조건 정량 검증."""
    d = json.loads((OUT / "deadline_f1_breakdown.json").read_text(encoding="utf-8"))
    r = json.loads((OUT / "relative_time_normalization_errors.json").read_text(encoding="utf-8"))
    enter = (d["deadline_f1"] < 0.85
             or r["relative_time_mismatch_rate"] > 0.10)
    # readiness 문서와 정합
    md = (OUT / "branch_d_readiness_quantitative.md").read_text(encoding="utf-8")
    assert f"enter_branch_d_main_pr: {enter}" in md
