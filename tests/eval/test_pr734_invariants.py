"""PR #734 Final Beta Readiness Measurement sentinel — #1~#13."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day28/final_beta_readiness_measurement"
D26 = ROOT / "evidence/day26/b2g_over_extraction_guard"


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


# ── #1 외부 베타 7+1 기준 종합 정합 (5/8) ────────────────────────────────
def test_외부_베타_7_1_기준_종합_정합():
    md = (OUT / "final_beta_readiness_assessment.md").read_text(encoding="utf-8")
    assert "5/8 충족" in md
    # 미달 3건 명시
    assert "strict_action_f1" in md and "dangerous_over_extraction_rate" in md


# ── #2 Controlled Beta 진입 불가 정직 ────────────────────────────────────
def test_controlled_beta_진입_불가_정직():
    d = _j("controlled_beta_decision_정량.json")
    assert d["decision"] == "진입 불가"
    assert d["msp_ge_0_80"] is False
    # PROCEED 금지 명시
    assert "PROCEED 금지" in d["decision_reason"]


# ── #3 Production Candidate 미달 정직 ────────────────────────────────────
def test_production_candidate_미달_정직():
    d = _j("production_candidate_path_정량.json")
    assert d["strict_action_f1_ge_0_90"] is False
    assert d["decision"] == "진입 불가"
    assert d["gap"] > 0


# ── #4 권위 측정 path 분명 안내 (option C) ───────────────────────────────
def test_권위_측정_path_분명_안내():
    d = _j("authoritative_measurement_path_정량.json")
    assert "option C" in d["authoritative_measurement"]
    assert d["instrumentation_ready"] is True
    assert len(d["next_steps"]) >= 3


# ── #5 잔여 A4 9건 후속 분기 정량 ────────────────────────────────────────
def test_잔여_A4_9건_후속_분기_정량():
    d = _j("residual_a4_9건_후속_분기_정량.json")
    assert d["residual_a4_count"] == 9
    assert len(d["residual_a4_ids"]) == 9
    # 4 옵션 + gold 수정 금지 옵션 명시
    opts = d["followup_options"]
    assert len(opts) == 4
    assert any(o.get("금지") for o in opts if o["option"] == "C")


# ── #6 main 측정값 변동 0 ────────────────────────────────────────────────
def test_main_측정값_변동_0():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["before"] == row["after"]
        assert row["delta"] == 0.0
    assert ba["safety_6_delta_zero"] is True


# ── #7 metric contract v2.0.0 유지 ───────────────────────────────────────
def test_metric_contract_v2_0_0_유지():
    d = _j("policy_drift_assessment.json")
    assert d["contract_version"] == "2.0.0"
    assert d["contract_version_changed"] is False
    assert d["drift_rate"] == 0.0


# ── #8 compute_readiness 재사용 (PR #733 helper) ─────────────────────────
def test_compute_readiness_재사용():
    d = _j("controlled_beta_decision_정량.json")
    assert d["compute_readiness_reused"] is True
    cr = d["compute_readiness_result"]
    assert cr["controlled_beta_ready"] == (cr["criteria_met_count"]
                                           == cr["criteria_total"])
    # import 가능 검증
    from scripts.eval.pr733_internal_alpha_feedback import compute_readiness
    assert callable(compute_readiness)


# ── #9 PR #733 alpha_feedback_schema 정합 ────────────────────────────────
def test_alpha_feedback_schema_정합():
    sch = json.loads((ROOT / "evidence/day27/internal_alpha_feedback"
                      / "alpha_feedback_schema_v1.json").read_text(encoding="utf-8"))
    assert sch["user_category_enum"] == ["accept", "dismiss", "irrelevant", "unsafe"]


# ── #10 새 측정 알고리즘 추가 0 (종합 PR — 선행 evidence 값 정합) ────────
def test_no_새_측정_알고리즘_추가():
    # 종합 PR — strict_action_f1 은 PR #732 evidence 값을 그대로 종합
    pr732 = json.loads((D26 / "before_after_strict_action_f1.json")
                       .read_text(encoding="utf-8"))["after"]
    ba = _j("before_after_main_metrics.json")
    saf = [r for r in ba["comparison"] if r["metric"] == "strict_action_f1"][0]
    assert saf["before"] == saf["after"] == pr732, "재측정 아님 — 선행 값 종합"


# ── #11 mixed_id_list dataset 누락 → fail-closed (Codex P1) ──────────────
def test_mixed_id_list_missing_from_dataset_fail_closed():
    from scripts.eval.pr734_final_beta_readiness_measurement import compute_coverage
    # s3 가 dataset 에서 누락
    cov = compute_coverage(["s1", "s2", "s3"], {"s1", "s2"}, ["s1", "s2", "s3"])
    assert cov["fail_class"] == "FULL_EVAL_COVERAGE_MISMATCH"
    assert cov["missing_count"] >= 1
    assert cov["missing_from_dataset_count"] >= 1
    assert "s3" in cov["missing_ids"]


# ── #12 mixed_id_list predictions 누락 → fail-closed (Codex P1) ──────────
def test_mixed_id_list_missing_from_predictions_fail_closed():
    from scripts.eval.pr734_final_beta_readiness_measurement import compute_coverage
    # s3 가 predictions 에서 누락
    cov = compute_coverage(["s1", "s2", "s3"], {"s1", "s2", "s3"}, ["s1", "s2"])
    assert cov["fail_class"] == "FULL_EVAL_COVERAGE_MISMATCH"
    assert cov["missing_count"] >= 1
    assert cov["missing_from_predictions_count"] >= 1


# ── #13 source/prediction duplicate fail-closed 유지 (PR #730 패턴 정합) ──
def test_source_prediction_duplicate_여전히_fail_closed_유지():
    from scripts.eval.pr734_final_beta_readiness_measurement import compute_coverage
    # source 중복 → SOURCE_SAMPLE_ID_DUPLICATE
    dup_src = compute_coverage(["s1", "s2", "s2"], {"s1", "s2"}, ["s1", "s2"])
    assert dup_src["fail_class"] == "SOURCE_SAMPLE_ID_DUPLICATE"
    # prediction 중복 → FULL_EVAL_COVERAGE_MISMATCH
    dup_pred = compute_coverage(["s1", "s2"], {"s1", "s2"}, ["s1", "s2", "s2"])
    assert dup_pred["fail_class"] == "FULL_EVAL_COVERAGE_MISMATCH"
    # 정상 → fail_class null
    ok = compute_coverage(["s1", "s2"], {"s1", "s2"}, ["s1", "s2"])
    assert ok["fail_class"] is None