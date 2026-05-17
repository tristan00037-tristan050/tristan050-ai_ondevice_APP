"""pr735_option_c_collection_plan.py — option C 수집 계획 (자문 6차 정합).

정식 Internal Alpha 배포 계획 + 권위 측정(option C) protocol 정착.
계획 PR — 측정값 변경 0, 새 측정 알고리즘 0, 알고리즘/prompt/model 변경 0.

자문 6차 정정: 최소 sample size 50 → 100/150/200 상향 (M-12).

verdict: MEASURED_ONLY (PROCEED 금지 — Controlled Beta 진입은 권위 측정 후).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.pr734_final_beta_readiness_measurement import (  # noqa: E402
    compute_coverage,
)

DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED_A = ROOT / "evidence/day19/branch_b3a_arbitration/mixed_a_67_six_subtype_classification.json"
OUT     = ROOT / "evidence/day29/option_c_collection_plan"

DATASET_ID = "card1_evalset_v1_1_500"
PR734_MERGE_SHA = "343c1f6f"
CONTRACT_VERSION = "2.0.0"

# ── 자문 6차 M-12 — 최소 sample size 상향 정정 (자문 5차 50건 → ) ──────────
SAMPLE_SIZE = {"minimum": 100, "recommended": 150, "strong_recommended": 200,
               "prior_자문5차": 50}
# ── 자문 6차 §10 — sample stratum 구성 ────────────────────────────────────
STRATUM_150 = {
    "residual_a4_ambiguous_request_report": 30,
    "a3_product_equivalent_suggestion": 40,
    "ordinary_safe_request": 30,
    "question_report_no_action_negative_controls": 30,
    "deadline_sensitive_cases": 20,
}
STRATUM_100 = {
    "residual_a4_a3": 40,
    "safe_request": 20,
    "negative_controls": 25,
    "deadline_sensitive": 15,
}
# ── 자문 6차 §3.4 — 4 카테고리 user feedback ─────────────────────────────
FEEDBACK_CATEGORIES = ["useful", "irrelevant", "unsafe", "needs_edit"]
# ── 자문 6차 §10 — reviewer 구성 ─────────────────────────────────────────
REVIEWER_CONFIG = {
    "minimum_reviewers": 2, "recommended_reviewers": 3,
    "adjudicator_required_if_2": True,
    "required_fields": ["reviewer_id", "sample_id", "rating", "confidence",
                        "reason_code", "adjudicated_label"],
}
# ── 자문 6차 §9 — Cohen's κ 개선 ─────────────────────────────────────────
KAPPA_TARGET = 0.70
KAPPA_PROXY_CURRENT = 0.6735      # PR #733 proxy κ (marginal 미달)
CALIBRATION_ROUND_SIZE = 10
# ── 자문 6차 §11 — Controlled Beta 진입 8 조건 ───────────────────────────
CONTROLLED_BETA_8_CONDITIONS = [
    {"id": 1, "condition": "authoritative_msp >= 0.80"},
    {"id": 2, "condition": "cohens_kappa >= 0.70"},
    {"id": 3, "condition": "unsafe_suggestion_rate <= 0.05"},
    {"id": 4, "condition": "dangerous_over_extraction_rate <= 0.05 "
                           "또는 user-visible dangerous case 0"},
    {"id": 5, "condition": "false_deadline_rate <= 0.02"},
    {"id": 6, "condition": "no_action_fp_rate <= 0.03"},
    {"id": 7, "condition": "auto_apply OFF 유지"},
    {"id": 8, "condition": "privacy audit PASS"},
]
# main 측정값 (계획 PR — 변동 0)
MAIN_METRICS = {"strict_action_f1": 0.6452, "deadline_f1": 0.8702,
                "action_fp": 207}


def _meta() -> Dict[str, Any]:
    return {"dataset_id": DATASET_ID, "source_pr": 735,
            "source_merge_sha": PR734_MERGE_SHA,
            "branch": "Option-C-Collection-Plan",
            "patch_type": "collection_plan_no_algorithm_no_measurement",
            "verdict": "MEASURED_ONLY"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # ── dataset integrity (PR #734 compute_coverage 재사용 — 무결성 확인) ──
    items = {}
    for line in DATASET.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            items[it["sample_id"]] = it
    pred_rows = [json.loads(line) for line in PREDS.open(encoding="utf-8")
                 if line.strip()]
    mixed = json.loads(MIXED_A.read_text(encoding="utf-8"))
    mixed_id_list = [r["sample_id"] for r in mixed["rows"]]
    pred_id_list = [p["sample_id"] for p in pred_rows]
    coverage = compute_coverage(mixed_id_list, set(items), pred_id_list)
    coverage["mode"] = "option_c_collection_plan"
    coverage["plan_pr_note"] = ("계획 PR — 신규 measurement 없음. dataset "
        "integrity 는 PR #730/#734 패턴으로 무결성만 확인.")
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                         ensure_ascii=False))
        return 1
    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── minimum_sample_size_정량 (자문 6차 M-12) ──
    assert sum(STRATUM_150.values()) == SAMPLE_SIZE["recommended"]
    assert sum(STRATUM_100.values()) == SAMPLE_SIZE["minimum"]
    (OUT / "minimum_sample_size_정량.json").write_text(json.dumps({
        **_meta(),
        "sample_size": SAMPLE_SIZE,
        "confidence_interval": "95%",
        "correction_note": ("자문 5차 6.5 (>= 50건) → 자문 6차 M-12 "
            "(최소 100 / 권장 150 / 강한 권장 200). 정정 근거: msp 비율 "
            "지표 안정성 — n=50 시 흔들림, n>=100 해석 가능."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── sample_stratum_구성 (자문 6차 §10) ──
    (OUT / "sample_stratum_구성.json").write_text(json.dumps({
        **_meta(),
        "stratum_150_recommended": STRATUM_150,
        "stratum_150_total": sum(STRATUM_150.values()),
        "stratum_100_minimum": STRATUM_100,
        "stratum_100_total": sum(STRATUM_100.values()),
        "sampling_protocol": ("stratum 별 결정적 추출 (sample_id 정렬) — "
            "PR #730 select_30 패턴 정합, RNG 미사용."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── controlled_beta_8조건_정량 (자문 6차 §11) ──
    (OUT / "controlled_beta_8조건_정량.json").write_text(json.dumps({
        **_meta(),
        "conditions": CONTROLLED_BETA_8_CONDITIONS,
        "condition_count": len(CONTROLLED_BETA_8_CONDITIONS),
        "entry_rule": ("8 조건 모두 충족 시에만 Controlled Beta 진입 정량 "
            "결정. 권위 측정(option C) 완료 후 별도 판정 PR. PROCEED 금지."),
        "current_status": ("proxy 측정 기준 진입 불가 (PR #734) — 권위 측정 "
            "전 진입 결정 불가 (자문 6차 M-10/M-13)."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── policy_drift_assessment (Standard 10) ──
    (OUT / "policy_drift_assessment.json").write_text(json.dumps({
        **_meta(), "policy_name": "card1 action metric contract",
        "contract_version": CONTRACT_VERSION, "contract_version_changed": False,
        "drift_rate": 0.0, "drift_class": "OK", "samples_compared": 0,
        "is_standard10_policy_drift_report": False,
        "drift_note": ("계획 PR — 측정/알고리즘 변경 0. metric contract "
            "v2.0.0 불변 (자문 6차 M-8 정합)."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── before_after_main_metrics ──
    (OUT / "before_after_main_metrics.json").write_text(json.dumps({
        **_meta(),
        "comparison": [{"metric": m, "before": v, "after": v, "delta": 0.0}
                       for m, v in MAIN_METRICS.items()],
        "safety_6_delta_zero": True,
        "reason": "계획 PR — 측정/알고리즘 변경 0 → main 측정값 변동 0.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── residual_a4_9건_후속_분기_정량_갱신 (자문 6차 M-5) ──
    (OUT / "residual_a4_9건_후속_분기_정량_갱신.json").write_text(json.dumps({
        **_meta(),
        "residual_a4_count": 9,
        "자문5차_4옵션": "옵션 A/B/D 권고 (병렬)",
        "자문6차_M5_정정": ("옵션 D 1순위 (Internal Alpha feedback 후 사용자 "
            "가치 판정) → 옵션 B (metric contract review) 순서."),
        "internal_alpha_feedback_target": True,
        "feedback_categories": FEEDBACK_CATEGORIES,
        "followup_pr": "별도 PR B (Residual A4 9 Review Protocol)",
        "gold_label_수정": "절대 금지 유지 (자문 4/5/6 M-3 명시)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── summary ──
    (OUT / "summary.md").write_text("\n".join([
        "# PR #735 — option C 수집 계획 Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 735\n"
        f"- branch: Option-C-Collection-Plan\n"
        f"- patch_type: collection_plan_no_algorithm_no_measurement\n"
        f"- verdict: MEASURED_ONLY",
        "",
        "## 본 PR 의 본질 (정직 보고)",
        "- 계획 PR — 정식 Internal Alpha 배포 계획 + option C 권위 측정 "
        "protocol 정착. 측정값 변경 0, 새 측정 알고리즘 0, 알고리즘/prompt/"
        "model 변경 0.",
        "- 카드 1 내부 알파 정식 진입 결정 (STATUS=ALPHA_PROMOTION) 후속 — "
        "auto_apply OFF + manual review only 절대 준수 (자문 6차 M-14).",
        "",
        "## 자문 5차 → 자문 6차 정정 정직 보고",
        f"- 최소 sample size: 자문 5차 50건 → 자문 6차 M-12 최소 "
        f"{SAMPLE_SIZE['minimum']} / 권장 {SAMPLE_SIZE['recommended']} / "
        f"강한 권장 {SAMPLE_SIZE['strong_recommended']}.",
        "- 잔여 A4 9건: 자문 5차 4 옵션 → 자문 6차 M-5 옵션 D 1순위.",
        "- semantic-aware guard: 자문 6차 §5 허용 형태 (post-hoc policy + "
        "warning + low_confidence marking) 정량 정의.",
        "- Controlled Beta 진입: 자문 6차 §11 8 조건 정량 명시.",
        "- reviewer 구성: 자문 6차 §10 최소 2명 + 권장 3명 + adjudicator.",
        "",
        "## option C 권위 측정 path",
        "- 4 카테고리 user feedback: useful / irrelevant / unsafe / needs_edit.",
        f"- 최소 {SAMPLE_SIZE['minimum']}건 / 권장 {SAMPLE_SIZE['recommended']}"
        f"건 stratum 구성.",
        f"- Cohen's κ 개선: 현 proxy {KAPPA_PROXY_CURRENT} → 권위 목표 "
        f">= {KAPPA_TARGET} (calibration round {CALIBRATION_ROUND_SIZE}건).",
        "- proxy 한계 정직 (Standard 12-H) — 권위 측정 전 Controlled Beta "
        "진입 결정 불가 (자문 6차 M-10/M-13).",
        "",
        "## main 측정값 정합 (변동 0)",
        "- strict_action_f1 0.6452 / deadline_f1 0.8702 / action_fp 207 / "
        "safety 6종 — 전부 불변. metric contract v2.0.0 유지.",
        "",
        "## verdict: MEASURED_ONLY",
        "계획 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "sample_size": SAMPLE_SIZE,
        "stratum_150_total": sum(STRATUM_150.values()),
        "stratum_100_total": sum(STRATUM_100.values()),
        "controlled_beta_conditions": len(CONTROLLED_BETA_8_CONDITIONS),
        "feedback_categories": FEEDBACK_CATEGORIES,
        "coverage_ok": coverage["fail_class"] is None,
        "verdict": "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
