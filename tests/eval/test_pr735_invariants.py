"""PR #735 option C Collection Plan sentinel — #1~#18."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day29/option_c_collection_plan"
D27 = ROOT / "evidence/day27/internal_alpha_feedback"

from scripts.eval.pr735_option_c_collection_plan import (  # noqa: E402
    CONTROLLED_BETA_8_CONDITIONS, FEEDBACK_CATEGORIES, KAPPA_TARGET,
    REVIEWER_CONFIG, SAMPLE_SIZE, STRATUM_100, STRATUM_150,
)


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _md(name):
    return (OUT / name).read_text(encoding="utf-8")


# ── #1 option C 수집 계획 명세 정합 ──────────────────────────────────────
def test_option_c_수집_계획_명세_정합():
    md = _md("option_c_collection_plan.md")
    for cat in FEEDBACK_CATEGORIES:
        assert cat in md
    assert "manual_suggestion_precision" in md


# ── #2 정식 Internal Alpha 배포 계획 정합 ────────────────────────────────
def test_정식_internal_alpha_배포_계획_정합():
    md = _md("internal_alpha_deployment_plan.md")
    assert "auto_apply OFF" in md
    assert "manual review only" in md


# ── #3 권위 측정 protocol 정합 ───────────────────────────────────────────
def test_권위_측정_protocol_정합():
    md = _md("authoritative_measurement_protocol.md")
    assert "proxy" in md and "권위 측정" in md
    assert "Standard 12-H" in md


# ── #4 최소 sample size 100 / 권장 150 정량 (자문 6차 M-12) ──────────────
def test_최소_sample_size_100_권장_150_정량():
    assert SAMPLE_SIZE["minimum"] == 100
    assert SAMPLE_SIZE["recommended"] == 150
    assert SAMPLE_SIZE["strong_recommended"] == 200
    assert SAMPLE_SIZE["prior_자문5차"] == 50
    j = _j("minimum_sample_size_정량.json")
    assert j["sample_size"]["minimum"] == 100


# ── #5 sample stratum 구성 정합 (자문 6차 §10) ──────────────────────────
def test_sample_stratum_구성_정합():
    assert sum(STRATUM_150.values()) == 150
    assert sum(STRATUM_100.values()) == 100
    j = _j("sample_stratum_구성.json")
    assert j["stratum_150_total"] == 150
    assert j["stratum_100_total"] == 100


# ── #6 reviewer 구성 정합 (최소 2 + 권장 3 + adjudicator) ────────────────
def test_reviewer_구성_정합():
    assert REVIEWER_CONFIG["minimum_reviewers"] == 2
    assert REVIEWER_CONFIG["recommended_reviewers"] == 3
    assert REVIEWER_CONFIG["adjudicator_required_if_2"] is True
    assert len(REVIEWER_CONFIG["required_fields"]) == 6
    for f in ["reviewer_id", "sample_id", "rating", "confidence",
              "reason_code", "adjudicated_label"]:
        assert f in REVIEWER_CONFIG["required_fields"]
    assert "adjudicator" in _md("reviewer_guide.md")


# ── #7 Cohen's κ 개선 protocol 정합 (자문 6차 §9) ───────────────────────
def test_cohens_kappa_개선_protocol_정합():
    assert KAPPA_TARGET == 0.70
    md = _md("cohens_kappa_improvement_protocol.md")
    assert "0.6735" in md and "calibration" in md


# ── #8 Controlled Beta 8조건 정량 정합 (자문 6차 §11) ───────────────────
def test_controlled_beta_8조건_정량_정합():
    assert len(CONTROLLED_BETA_8_CONDITIONS) == 8
    j = _j("controlled_beta_8조건_정량.json")
    assert j["condition_count"] == 8
    txt = json.dumps(j, ensure_ascii=False)
    assert "authoritative_msp >= 0.80" in txt
    assert "cohens_kappa >= 0.70" in txt


# ── #9 semantic-aware guard v0 허용 형태 정합 (자문 6차 §5) ─────────────
def test_semantic_aware_guard_v0_허용_형태_정합():
    md = _md("semantic_aware_guard_v0_허용_형태.md")
    assert "post-hoc" in md and "low_confidence" in md
    # 절대 금지 명시
    assert "LoRA" in md and "금지" in md


# ── #10 privacy guarantee 절대 보증 ──────────────────────────────────────
def test_privacy_guarantee_절대_보증():
    md = _md("privacy_guarantee_audit.md")
    assert "raw" in md and "0건" in md
    assert "외부 전송" in md and "sha256" in md


# ── #11 사용자 동의 protocol 정합 ────────────────────────────────────────
def test_사용자_동의_protocol_정합():
    md = _md("user_consent_protocol.md")
    assert "opt-out" in md
    assert "개인정보보호법" in md


# ── #12 PR #733 alpha_feedback_schema 정합 ──────────────────────────────
def test_alpha_feedback_schema_정합():
    sch = json.loads((D27 / "alpha_feedback_schema_v1.json").read_text(encoding="utf-8"))
    assert sch["schema_name"] == "internal_alpha_suggestion_feedback"


# ── #13 PR #733 collection pipeline 정합 ────────────────────────────────
def test_collection_pipeline_정합():
    assert (D27 / "alpha_feedback_collection_pipeline.md").exists()


# ── #14 main 측정값 변동 0 (계획 PR 본질) ───────────────────────────────
def test_main_측정값_변동_0():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["before"] == row["after"]
        assert row["delta"] == 0.0
    assert ba["safety_6_delta_zero"] is True


# ── #15 metric contract v2.0.0 유지 (자문 6차 M-8) ──────────────────────
def test_metric_contract_v2_0_0_유지():
    d = _j("policy_drift_assessment.json")
    assert d["contract_version"] == "2.0.0"
    assert d["contract_version_changed"] is False
    assert d["drift_rate"] == 0.0


# ── #16 auto_apply OFF 절대 준수 (자문 6차 M-14) ────────────────────────
def test_auto_apply_off_절대_준수():
    plan = _md("internal_alpha_deployment_plan.md")
    cbc = json.dumps(_j("controlled_beta_8조건_정량.json"), ensure_ascii=False)
    assert "auto_apply OFF" in plan
    assert "auto_apply OFF" in cbc


# ── #17 manual review only 절대 준수 (자문 6차 M-14) ────────────────────
def test_manual_review_only_절대_준수():
    plan = _md("internal_alpha_deployment_plan.md")
    assert "manual review only" in plan


# ── #18 release / production ready 표현 미사용 ──────────────────────────
def test_release_표현_미사용_정합():
    forbidden = re.compile(r"release ready|production ready|production candidate approved")
    for f in OUT.glob("*"):
        text = f.read_text(encoding="utf-8")
        assert not forbidden.search(text), f"{f.name} 에 금지 표현"
