"""PR #725 Branch B-3A arbitration measurement sentinel."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "evidence/day19/branch_b3a_arbitration"
SCRIPT = ROOT / "scripts/eval/pr725_branch_b3a_arbitration.py"


def _load_module():
    """pr725_branch_b3a_arbitration 모듈 로드 (__main__ 가드로 main() 미실행)."""
    spec = importlib.util.spec_from_file_location(
        "pr725_branch_b3a_arbitration", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


# ── Codex P1/P2 정정 회귀 sentinel ───────────────────────────────────────
def test_prediction_missing_sample_id_fail_closed(tmp_path):
    """#6 — preds 에 sample_id 누락 시 FULL_EVAL_COVERAGE_MISMATCH fail-closed."""
    mod = _load_module()
    items = [{"sample_id": "S001"}, {"sample_id": "S002"}, {"sample_id": "S003"}]
    preds = [{"sample_id": "S001"}, {"sample_id": "S002"}]   # S003 누락
    with pytest.raises(SystemExit):
        mod.check_coverage(items, preds, tmp_path)
    cov = json.loads((tmp_path / "coverage_report.json").read_text(encoding="utf-8"))
    assert cov["fail_class"] == "FULL_EVAL_COVERAGE_MISMATCH"
    assert cov["missing_count"] > 0
    assert "S003" in cov["missing_ids"]


def test_prediction_duplicate_sample_id_fail_closed(tmp_path):
    """#7 — preds 에 duplicate sample_id 시 FULL_EVAL_COVERAGE_MISMATCH fail-closed."""
    mod = _load_module()
    items = [{"sample_id": "S001"}, {"sample_id": "S002"}]
    preds = [{"sample_id": "S001"}, {"sample_id": "S002"}, {"sample_id": "S002"}]
    with pytest.raises(SystemExit):
        mod.check_coverage(items, preds, tmp_path)
    cov = json.loads((tmp_path / "coverage_report.json").read_text(encoding="utf-8"))
    assert cov["fail_class"] == "FULL_EVAL_COVERAGE_MISMATCH"
    assert cov["prediction_duplicate_count"] > 0
    assert "S002" in cov["prediction_duplicate_ids"]


def test_blank_evidence_action_text_not_matched():
    """#8 — evidence/action_text 가 모두 빈 action 은 matched 로 계산되지 않는다."""
    mod = _load_module()
    text = "회의 자료를 금요일까지 보내주세요"
    pred = {"actions": [
        {"evidence": "",          "action_text": ""},                  # blank
        {"evidence": "회의 자료", "action_text": ""},                   # matched
        {"evidence": "",          "action_text": "존재하지 않는 문구"},  # not matched
    ]}
    score, blank_count = mod.evidence_score(text, pred)
    assert blank_count == 1
    # blank action 은 matched 0 처리 → matched 1 / 3 actions
    assert score == round(1 / 3, 4)
    # 이전 버그라면 blank 가 '"" in text' == True 로 과대평가됨
    assert score < 1.0
