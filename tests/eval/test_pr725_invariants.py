"""PR #725 Branch B-3A arbitration measurement sentinel."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "evidence/day19/branch_b3a_arbitration"


def test_mixed_a_67_subtype_coverage():
    """MIXED-A 67건 6 subtype 분류 합계 = 67."""
    c = json.loads((OUT / "mixed_a_67_six_subtype_classification.json").read_text(encoding="utf-8"))
    assert c["mixed_a_total"] == 67
    assert sum(c["subtype_distribution"].values()) == 67
    # 모든 subtype 키는 MIXED-A1~A6 영역
    for st in c["subtype_distribution"]:
        assert st.startswith("MIXED-A"), f"unexpected subtype {st}"


def test_field_level_comparison_consistency():
    """parser_wins + llm_wins + tie = mixed_a_total."""
    f = json.loads((OUT / "field_level_comparison_results.json").read_text(encoding="utf-8"))
    assert (f["parser_wins"] + f["llm_wins"] + f["tie"]) == f["mixed_a_total"]
    for r in f["rows"]:
        assert r["parser_field_score"] <= r["field_total"]
        assert r["llm_field_score"] <= r["field_total"]


def test_evidence_score_range():
    """evidence_score 0.0~1.0 범위."""
    e = json.loads((OUT / "evidence_aware_arbitration_simulation.json").read_text(encoding="utf-8"))
    assert 0.0 <= e["avg_evidence_score"] <= 1.0
    for r in e["evidence_scores"]:
        assert 0.0 <= r["evidence_score"] <= 1.0


def test_recovery_potential_bounded():
    """total_estimated_recoverable ≤ mixed_a_total."""
    r = json.loads((OUT / "recovery_potential_estimation.json").read_text(encoding="utf-8"))
    assert r["total_estimated_recoverable"] <= r["mixed_a_total"]
    for st, v in r["subtype_recovery"].items():
        assert 0.0 <= v["avg_recoverable_estimate"] <= 1.0


def test_pr725_verdict_measured_only():
    """측정 PR — verdict 는 MEASURED_ONLY 만 허용."""
    for f in ["mixed_a_67_six_subtype_classification.json",
              "field_level_comparison_results.json",
              "evidence_aware_arbitration_simulation.json",
              "recovery_potential_estimation.json"]:
        obj = json.loads((OUT / f).read_text(encoding="utf-8"))
        assert obj["verdict"] == "MEASURED_ONLY", f"{f} verdict != MEASURED_ONLY"
