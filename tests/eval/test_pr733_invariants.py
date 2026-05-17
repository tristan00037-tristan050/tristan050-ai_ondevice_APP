"""PR #733 Internal Alpha Feedback Instrumentation sentinel — #1~#16."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day27/internal_alpha_feedback"

from scripts.eval.pr733_internal_alpha_feedback import (  # noqa: E402
    FEEDBACK_CATEGORIES, MAIN_SAFETY, _digest, cohens_kappa,
    compute_readiness, msp,
)


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


# ── #1 schema 4 카테고리 enum ────────────────────────────────────────────
def test_alpha_feedback_schema_4_카테고리():
    sch = _j("alpha_feedback_schema_v1.json")
    assert sch["user_category_enum"] == ["accept", "dismiss", "irrelevant", "unsafe"]
    assert FEEDBACK_CATEGORIES == ["accept", "dismiss", "irrelevant", "unsafe"]


# ── #2 digest 저장 (raw text 0건) ────────────────────────────────────────
def test_alpha_feedback_digest_저장():
    d = _digest("회의 결과 공유드립니다")
    assert d.startswith("sha256:")
    assert "회의" not in d
    # feedback 레코드는 digest 필드만 — raw text 필드 부재
    rep = _j("reviewer_feedback_result.json")
    for rec in rep["feedback_records"]:
        assert rec["suggestion_context_digest"].startswith("sha256:")
        assert "text" not in rec and "raw_text" not in rec


# ── #3 외부 전송 차단 ────────────────────────────────────────────────────
def test_alpha_feedback_외부_전송_차단():
    sch = _j("alpha_feedback_schema_v1.json")
    assert "internal only" in sch["transmission"]
    audit = (OUT / "alpha_feedback_privacy_audit.md").read_text(encoding="utf-8")
    assert "외부 전송" in audit and "egress 0" in audit


# ── #4 manual_suggestion_precision 산식 ──────────────────────────────────
def test_manual_suggestion_precision_산식():
    # accept / (accept+dismiss+irrelevant+unsafe)
    assert msp({"accept": 8, "dismiss": 1, "irrelevant": 1, "unsafe": 0}) == 0.8
    assert msp({"accept": 0, "dismiss": 0, "irrelevant": 0, "unsafe": 0}) == 0.0
    rep = _j("reviewer_feedback_result.json")
    sc = rep["reviewer_strict"]["counts"]
    expect = round(sc.get("accept", 0) / sum(sc.values()), 4)
    assert rep["reviewer_strict"]["manual_suggestion_precision"] == expect


# ── #5 Cohen's κ 산식 정합 ───────────────────────────────────────────────
def test_cohens_kappa_정합():
    # 완전 일치 → κ = 1.0
    assert cohens_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    # evidence κ 가 [-1, 1] 범위
    ck = _j("cohens_kappa_consistency.json")
    assert -1.0 <= ck["cohens_kappa"] <= 1.0
    assert ck["kappa_meets_threshold"] == (ck["cohens_kappa"] >= 0.7)


# ── #6 auto_apply OFF ────────────────────────────────────────────────────
def test_auto_apply_OFF_정합():
    sch = _j("alpha_feedback_schema_v1.json")
    assert "OFF" in sch["auto_apply"]


# ── #7 audit log 정합 (모든 feedback 기록) ───────────────────────────────
def test_audit_log_정합():
    rep = _j("reviewer_feedback_result.json")
    recs = rep["feedback_records"]
    assert all(r.get("audit_log_id") for r in recs)
    # audit_log_id 는 feedback 와 1:1 (중복 없음)
    ids = [r["audit_log_id"] for r in recs]
    assert len(ids) == len(set(ids))


# ── #8 main 측정값 변동 0 ────────────────────────────────────────────────
def test_main_측정값_변동_0():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["before"] == row["after"]
        assert row["delta"] == 0.0
    assert ba["safety_6_delta_zero"] is True


# ── #9 metric contract v2.0.0 유지 ───────────────────────────────────────
def test_metric_contract_v2_0_0_유지():
    pda = _j("policy_drift_assessment.json")
    assert pda["contract_version"] == "2.0.0"
    assert pda["contract_version_changed"] is False
    assert pda["drift_rate"] == 0.0


# ── #10 privacy audit (raw text 저장 0건) ────────────────────────────────
def test_privacy_audit_정합():
    rep = _j("reviewer_feedback_result.json")
    # 어떤 feedback 레코드에도 원문이 직렬화되어 있지 않음
    blob = json.dumps(rep["feedback_records"], ensure_ascii=False)
    assert "공유드립니다" not in blob and "알 수 있을까요" not in blob


# ── #11 alpha feedback 을 production decision 직접 반영 0 ────────────────
def test_no_alpha_feedback_to_production_direct():
    cb = _j("controlled_beta_readiness_assessment.json")
    # Controlled Beta 진입 결정은 별도 PR — PROCEED 금지 명시
    assert "별도" in cb["decision_note"]
    # 계측 PR — metric contract drift 0 (feedback 이 평가 산식에 미반영)
    pda = _j("policy_drift_assessment.json")
    assert pda["drift_rate"] == 0.0


# ── #12 Controlled Beta readiness 정량 평가 ──────────────────────────────
def test_controlled_beta_readiness_정합():
    cb = _j("controlled_beta_readiness_assessment.json")
    assert cb["criteria_total"] == 7
    assert cb["criteria_met_count"] == sum(cb["criteria"].values())
    assert cb["controlled_beta_ready"] == all(cb["criteria"].values())
    # 미충족 시 blocking_criteria 에 정직 명시
    assert set(cb["blocking_criteria"]) == \
        {k for k, v in cb["criteria"].items() if not v}


# ── #13 readiness gate — false_deadline_rate fail-open 차단 (Codex P1) ───
def test_readiness_gate_false_deadline_rate_fail_open_차단():
    # metric regression (0.021 > 0.02) → gate False, fail-closed
    r = compute_readiness({"false_deadline_rate": 0.021,
                           "no_action_fp_rate": 0.0273})
    assert r["criteria"]["false_deadline_rate <= 0.02"] is False
    assert r["controlled_beta_ready"] is False


# ── #14 readiness gate — no_action_fp_rate fail-open 차단 (Codex P1) ─────
def test_readiness_gate_no_action_fp_rate_fail_open_차단():
    r = compute_readiness({"false_deadline_rate": 0.014,
                           "no_action_fp_rate": 0.031})
    assert r["criteria"]["no_action_fp_rate <= 0.03"] is False
    assert r["controlled_beta_ready"] is False


# ── #15 readiness gate — 정상 metric 값 정합 ────────────────────────────
def test_readiness_gate_정상값_정합():
    r = compute_readiness(MAIN_SAFETY)
    assert r["criteria"]["false_deadline_rate <= 0.02"] is True
    assert r["criteria"]["no_action_fp_rate <= 0.03"] is True
    # gate 가 실제 metric 에서 산출 (hardcoded True 아님)
    ce = r["criteria_evaluation"]["false_deadline_rate <= 0.02"]
    assert ce["metric_value"] == MAIN_SAFETY["false_deadline_rate"]
    assert ce["metric_source"].startswith("PR #732")


# ── #16 controlled_beta_ready == all(criteria) 정합 ─────────────────────
def test_controlled_beta_ready_all_criteria_정합():
    r = compute_readiness(MAIN_SAFETY)
    assert r["controlled_beta_ready"] == all(r["criteria"].values())
    assert r["criteria_met_count"] == sum(r["criteria"].values())
    # 현재: strict_action_f1 / msp 미충족 → 5/7, ready False
    assert r["controlled_beta_ready"] is False
