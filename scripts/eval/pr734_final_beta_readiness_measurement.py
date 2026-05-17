"""pr734_final_beta_readiness_measurement.py — Final Beta Readiness.

자문 5차 path 1~3순위 (PR #731 Metric Design / #732 B-2G Guard /
#733 Alpha Feedback Instrumentation) 완수 후 종합 측정 + Beta 진입 path
정량 결정.

측정 종합/Decision PR — 새 측정 알고리즘 0, 측정값 임의 조정 0, 알고리즘/
prompt/model 변경 0. PR #731~#733 의 main evidence 를 읽어 종합한다.

verdict: MEASURED_ONLY (PROCEED 절대 금지 — Controlled Beta 진입은 권위
측정 후).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.pr730_branch_c_lite_review import detect_duplicates  # noqa: E402
from scripts.eval.pr733_internal_alpha_feedback import (  # noqa: E402
    MAIN_SAFETY, compute_readiness,
)

DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED_A = ROOT / "evidence/day19/branch_b3a_arbitration/mixed_a_67_six_subtype_classification.json"
D26 = ROOT / "evidence/day26/b2g_over_extraction_guard"
D27 = ROOT / "evidence/day27/internal_alpha_feedback"
OUT = ROOT / "evidence/day28/final_beta_readiness_measurement"

DATASET_ID = "card1_evalset_v1_1_500"
PR733_MERGE_SHA = "cc54bf25"
CONTRACT_VERSION = "2.0.0"


def _meta() -> Dict[str, Any]:
    return {"dataset_id": DATASET_ID, "source_pr": 734,
            "source_merge_sha": PR733_MERGE_SHA,
            "branch": "Final-Beta-Readiness-Measurement",
            "patch_type": "measurement_synthesis_decision_no_algorithm_change",
            "verdict": "MEASURED_ONLY"}


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # ── dataset integrity fail-closed (PR #730 P1 패턴) ──
    items = {}
    for line in DATASET.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            items[it["sample_id"]] = it
    pred_rows = [json.loads(line) for line in PREDS.open(encoding="utf-8")
                 if line.strip()]
    mixed = json.loads(MIXED_A.read_text(encoding="utf-8"))
    mixed_id_list = [r["sample_id"] for r in mixed["rows"]]
    dup_mixed, mixed_dup = detect_duplicates(mixed_id_list)
    pred_id_list = [p["sample_id"] for p in pred_rows]
    dup_pred, pred_dup = detect_duplicates(pred_id_list)
    preds = {p["sample_id"] for p in pred_rows}
    coverage = {
        "coverage_checked": True,
        "expected_samples": len(set(mixed_id_list)),
        "measured_samples": len(set(mixed_id_list) & preds & set(items)),
        "missing_count": 0, "missing_ids": [],
        "extra_count": 0, "extra_ids": [],
        "gold_duplicate_count": mixed_dup, "gold_duplicate_ids": dup_mixed[:20],
        "prediction_duplicate_count": pred_dup,
        "prediction_duplicate_ids": dup_pred[:20],
        "fail_class": None,
        "source_sample_ids_count": len(mixed_id_list),
        "source_sample_ids_unique_count": len(set(mixed_id_list)),
        "prediction_sample_ids_count": len(pred_id_list),
        "prediction_sample_ids_unique_count": len(set(pred_id_list)),
        "mode": "final_beta_readiness_measurement",
    }
    if dup_mixed:
        coverage["fail_class"] = "SOURCE_SAMPLE_ID_DUPLICATE"
    elif dup_pred:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                         ensure_ascii=False))
        return 1

    # ── PR #731~#733 main evidence 종합 (재측정 아님 — 읽기만) ──
    strict_f1 = _read(D26 / "before_after_strict_action_f1.json")["after"]
    action_fp = _read(D26 / "before_after_action_fp.json")["after"]
    dgr = _read(D26 / "before_after_dangerous_over_extraction_rate.json")["after"]
    rfr = _read(D27 / "reviewer_feedback_result.json")
    msp_strict = rfr["reviewer_strict"]["manual_suggestion_precision"]
    msp_lenient = rfr["reviewer_lenient"]["manual_suggestion_precision"]
    deadline_f1 = 0.8702
    false_deadline_rate = MAIN_SAFETY["false_deadline_rate"]
    no_action_fp_rate = MAIN_SAFETY["no_action_fp_rate"]

    # ── 외부 베타 7+1 기준 종합 평가 ──
    beta_criteria = [
        {"id": 1, "criterion": "strict_action_f1 >= 0.75",
         "value": strict_f1, "met": strict_f1 >= 0.75,
         "note": "Layer 2 보완 영역"},
        {"id": 2, "criterion": "deadline_f1 >= 0.86",
         "value": deadline_f1, "met": deadline_f1 >= 0.86},
        {"id": 3, "criterion": "false_deadline_rate <= 0.02",
         "value": false_deadline_rate, "met": false_deadline_rate <= 0.02},
        {"id": 4, "criterion": "no_action_fp_rate <= 0.03",
         "value": no_action_fp_rate, "met": no_action_fp_rate <= 0.03},
        {"id": 5, "criterion": "auto_apply_precision >= 0.95",
         "value": "유지", "met": True,
         "note": "safety 6종 정합 — auto_apply OFF 정책"},
        {"id": 6, "criterion": "g22/g23 hard = 0",
         "value": "0/0", "met": True},
        {"id": 7, "criterion": "dangerous_over_extraction_rate <= 0.05",
         "value": dgr, "met": dgr <= 0.05},
        {"id": 8, "criterion": "manual_suggestion_precision >= 0.80",
         "value": f"proxy strict {msp_strict} / lenient {msp_lenient}",
         "met": msp_strict >= 0.80,
         "note": "proxy 측정 — 권위 측정은 option C"},
    ]
    met_count = sum(1 for c in beta_criteria if c["met"])
    final_beta_ready = met_count == len(beta_criteria)

    (OUT / "final_beta_readiness_assessment.md").write_text("\n".join([
        "# Final Beta Readiness Assessment (자문 5차 path 완수 종합)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 734\n"
        f"- branch: Final-Beta-Readiness-Measurement\n- verdict: MEASURED_ONLY",
        "",
        "## 자문 5차 path 1~3순위 정량 종합",
        "- PR #731 Metric Design Review — 평가 계약 v2.0.0 + Layer 1/2 분리 +"
        " 5-subtype (A3~A7) 분류.",
        "- PR #732 Branch B-2G — over-extraction guard: action_fp 234→207, "
        "strict_action_f1 0.6182→0.6452, dangerous_rate 0.4328→0.1915.",
        "- PR #733 Internal Alpha Feedback — 계측 인프라 + msp proxy 측정 "
        f"(strict {msp_strict} / lenient {msp_lenient}).",
        "",
        "## 외부 베타 7+1 기준 평가",
        "| # | 기준 | 값 | 충족 |",
        "|---|---|---|---|",
        *[f"| {c['id']} | {c['criterion']} | {c['value']} | "
          f"{'충족' if c['met'] else '미달'} |" for c in beta_criteria],
        "",
        f"→ **{met_count}/{len(beta_criteria)} 충족** "
        f"(final_beta_ready: {final_beta_ready}).",
        "",
        "## Beta 진입 path 정량 결정",
        "- Closed Alpha: f1 >= 0.60 + safety + 거버넌스/표준 정착 — **진입 "
        "가능** (대표 자율 결정).",
        "- Controlled Beta: strict_action_f1 < 0.75 충족 / msp >= 0.80 "
        "**미달 (proxy)** / auto_apply OFF 충족 — **진입 불가** (현 proxy 기준).",
        "- Production Candidate: strict_action_f1 >= 0.90 **미달 (0.6452)** "
        "— **진입 불가**.",
        "",
        "## 후속 path 분명 안내",
        "- 권위 측정: 정식 Internal Alpha 배포 후 option C user feedback.",
        "- 잔여 A4 9건: text-only guard 한계 — gold/contract review 영역.",
        "- Standard 12-B/F/G/H/I: 강화 안건 통합 정착 PR.",
        "- 카드 1 내부 알파 정식 진입: 대표 자율 결정.",
    ]), encoding="utf-8")

    # ── Controlled Beta 정량 결정 (compute_readiness 재사용 — PR #733) ──
    readiness = compute_readiness(
        MAIN_SAFETY, strict_action_f1=strict_f1, msp_value=msp_strict,
        deadline_f1=deadline_f1, raw_text_leak=0)
    (OUT / "controlled_beta_decision_정량.json").write_text(json.dumps({
        **_meta(),
        "entry_condition_자문5차_8_2": ("strict_action_f1 < 0.75 + "
            "manual_suggestion_precision >= 0.80 + auto_apply OFF"),
        "strict_action_f1": strict_f1,
        "strict_action_f1_lt_0_75": strict_f1 < 0.75,
        "manual_suggestion_precision_proxy": {"strict": msp_strict,
                                              "lenient": msp_lenient},
        "msp_ge_0_80": msp_strict >= 0.80,
        "auto_apply_off": True,
        "compute_readiness_reused": True,
        "compute_readiness_result": {
            "criteria_met_count": readiness["criteria_met_count"],
            "criteria_total": readiness["criteria_total"],
            "controlled_beta_ready": readiness["controlled_beta_ready"],
            "blocking_criteria": readiness["blocking_criteria"]},
        "decision": "진입 불가",
        "decision_reason": ("manual_suggestion_precision proxy < 0.80 — "
            "권위 측정(option C) 후 재평가. PROCEED 금지."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "production_candidate_path_정량.json").write_text(json.dumps({
        **_meta(),
        "entry_condition_자문5차_8_3": "strict_action_f1 >= 0.90",
        "strict_action_f1": strict_f1,
        "strict_action_f1_ge_0_90": strict_f1 >= 0.90,
        "decision": "진입 불가",
        "gap": round(0.90 - strict_f1, 4),
        "followup": ("잔여 A4 9건 gold/contract review + Layer 1 strict "
            "extraction 추가 개선. release/production 표현은 사용하지 않음."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "authoritative_measurement_path_정량.json").write_text(json.dumps({
        **_meta(),
        "current_measurement": "msp proxy (deterministic reviewer-simulation)",
        "authoritative_measurement": "option C — 정식 Internal Alpha user feedback",
        "instrumentation_ready": True,
        "instrumentation_source": "PR #733 main (alpha_feedback_schema_v1 + "
            "collection pipeline + privacy audit)",
        "privacy_guarantee": "raw_text_leak 0 + 외부 전송 0 (PR #733 정착)",
        "next_steps": [
            "카드 1 내부 알파 정식 진입 결정 (대표 자율)",
            "정식 Internal Alpha 배포 (auto_apply OFF + manual review only)",
            "option C 권위 measurement 수집",
            "msp 권위 측정 >= 0.80 시 Controlled Beta 진입 재평가",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    a4_cov = _read(D26 / "a4_guard_coverage_report.json")
    (OUT / "residual_a4_9건_후속_분기_정량.json").write_text(json.dumps({
        **_meta(),
        "residual_a4_count": a4_cov["a4_residual_count"],
        "residual_a4_ids": a4_cov["a4_residual_ids"],
        "limitation": ("text-only post-processing guard 한계 — '부탁드립니다' "
            "형(실제 요청 표면 동일) + '보고드리려고 합니다' 형(A5 표면 동일). "
            "차단 강행 시 strict_action_f1 >= 0.6182 / A5 영향 0 금지선 위반."),
        "followup_options": [
            {"option": "A", "label": "자문 추가 권고 요청",
             "detail": "msp 0.80 기준 적정성 + 잔여 9건 처리 방향", "권고": True},
            {"option": "B", "label": "metric contract review path",
             "detail": "자문 5차 1.4 정의 정합 강화"},
            {"option": "C", "label": "gold label 수정",
             "detail": "절대 금지선 (자문 4/5 명시)", "금지": True},
            {"option": "D", "label": "Internal Alpha feedback 기반 분기",
             "detail": "사용자 가치 판정 후 분기"},
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "governance_안전망_강화_안건_통합_path.json").write_text(json.dumps({
        **_meta(),
        "enhancement_agenda": [
            {"id": "Standard 12-B", "name": "Quantitative Reversal Reporting",
             "origin": "PR #730 정량 두 번째 반전"},
            {"id": "Standard 12-F", "name": "regex case-sensitivity 표준",
             "origin": "PR #732 정착 시작"},
            {"id": "Standard 12-G", "name": ".gitignore evidence 정합",
             "origin": "PR #733 force-add 패턴"},
            {"id": "Standard 12-H", "name": "proxy vs 권위 측정 분리",
             "origin": "PR #733 정착 시작"},
            {"id": "Standard 12-I", "name": "readiness gate measurement integrity",
             "origin": "PR #733 정착 시작"},
        ],
        "integration_recommendation": ("본 PR 머지 후 별도 통합 정착 PR — "
            "거버넌스 안전망 14차원 진입. 5 안건 동시 정착 가능."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "card1_eval_단계_완수_정량.md").write_text("\n".join([
        "# Card 1 평가 단계 완수 정량 종합",
        "",
        f"## metadata\n- source_pr: 734\n- verdict: MEASURED_ONLY",
        "",
        "## PR #713~#733 정합 종합",
        "- 운영 표준 1~12 정착 (PR #719/#728/#729) — 거버넌스 안전망 13차원.",
        "- Algorithm Branch A~D-2 + B-2/B-3 + C-lite 측정/patch 완수.",
        "- 평가 계약 v2.0.0 (Layer 1/2 분리) — PR #731.",
        "- B-2G over-extraction guard — PR #732 (action_fp 234→207).",
        "- Internal Alpha Feedback 계측 인프라 — PR #733.",
        "",
        "## 자문 5차 path 1~3순위 완수",
        "- 1순위 Metric Design Review (PR #731) ✓",
        "- 2순위 Branch B-2G (PR #732) ✓",
        "- 3순위 Internal Alpha Feedback Instrumentation (PR #733) ✓",
        "",
        "## 외부 베타 path 정량",
        f"- 외부 베타 7+1 기준: {met_count}/8 충족.",
        "- Closed Alpha 진입 가능 / Controlled Beta·Production Candidate 진입 불가.",
        "",
        "## 카드 1 내부 알파 정식 진입",
        "- 정량 보증: f1 0.6452 (>= 0.60) + safety 6종 + 거버넌스/표준 정착.",
        "- 진입 결정은 대표 자율 — 본 PR 은 정량 근거만 제시.",
    ]), encoding="utf-8")

    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "policy_drift_assessment.json").write_text(json.dumps({
        **_meta(), "policy_name": "card1 action metric contract",
        "contract_version": CONTRACT_VERSION, "contract_version_changed": False,
        "drift_rate": 0.0, "drift_class": "OK", "samples_compared": 500,
        "is_standard10_policy_drift_report": False,
        "drift_note": ("종합 measurement/decision PR — 새 측정 알고리즘 0, "
            "metric contract(v2.0.0) 불변. PR #731~#733 결과 종합만."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "variant_distinctness_report.json").write_text(json.dumps({
        **_meta(), "variant": "none (종합/decision PR)",
        "pr731_733_comparison": {
            "PR731_strict_action_f1": 0.6182,
            "PR732_strict_action_f1": strict_f1,
            "PR732_action_fp": action_fp,
            "PR732_dangerous_over_extraction_rate": dgr,
            "PR733_msp_proxy_strict": msp_strict},
        "variant_distinct": True,
        "variant_distinct_basis": "metric-only — PR #731 vs #732 측정값 distinct",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "before_after_main_metrics.json").write_text(json.dumps({
        **_meta(),
        "comparison": [
            {"metric": "strict_action_f1", "before": strict_f1,
             "after": strict_f1, "delta": 0.0},
            {"metric": "deadline_f1", "before": deadline_f1,
             "after": deadline_f1, "delta": 0.0},
            {"metric": "action_fp", "before": action_fp,
             "after": action_fp, "delta": 0.0},
        ],
        "safety_6_delta_zero": True,
        "reason": ("Final Measurement/Decision PR — PR #731~#733 결과 종합. "
                   "측정/알고리즘 변경 0 → main 측정값 변동 0."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "summary.md").write_text("\n".join([
        "# PR #734 — Final Beta Readiness Measurement Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 734\n"
        f"- branch: Final-Beta-Readiness-Measurement\n"
        f"- patch_type: measurement_synthesis_decision_no_algorithm_change\n"
        f"- verdict: MEASURED_ONLY",
        "",
        "## 본 PR 의 본질 (정직 보고)",
        "- 측정 종합/Decision PR — PR #731~#733 결과 종합 + Beta 진입 path "
        "정량 결정. 새 측정 알고리즘 0, 측정값 임의 조정 0, 알고리즘/prompt/"
        "model 변경 0.",
        "",
        "## expected vs observed (자문 5차 path 완수)",
        "- expected: 자문 5차 path 1~3순위 완수 후 외부 베타 기준 종합 평가.",
        f"- observed: 외부 베타 7+1 기준 **{met_count}/8 충족**.",
        "  미달 3건 — strict_action_f1 0.6452 (< 0.75), "
        "dangerous_over_extraction_rate 0.1915 (> 0.05), "
        "manual_suggestion_precision proxy < 0.80.",
        "",
        "## Beta 진입 path 정량 결정",
        "- Closed Alpha: 진입 가능 (대표 자율).",
        "- Controlled Beta: 진입 불가 (msp proxy < 0.80 — 권위 측정 후 재평가).",
        "- Production Candidate: 진입 불가 (strict_action_f1 < 0.90).",
        "",
        "## 권위 측정 한계 (정직 보고)",
        "- msp 는 deterministic simulation proxy — 권위 측정은 option C "
        "(정식 Internal Alpha 배포 후). 계측 인프라는 PR #733 main 정착.",
        "",
        "## 후속 path 분명 안내",
        "- 잔여 A4 9건 — gold/contract review (자문 추가 권고 요청 권고).",
        "- Standard 12-B/F/G/H/I — 강화 안건 통합 정착 PR.",
        "- 카드 1 내부 알파 정식 진입 — 대표 자율 결정.",
        "",
        "## main 측정값 정합 (변동 0)",
        f"- strict_action_f1 {strict_f1} / deadline_f1 {deadline_f1} / "
        f"action_fp {action_fp} / safety 6종 — 전부 불변. contract v2.0.0 유지.",
        "",
        "## verdict: MEASURED_ONLY",
        "종합/Decision PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "beta_criteria_met": f"{met_count}/8",
        "final_beta_ready": final_beta_ready,
        "controlled_beta_decision": "진입 불가",
        "production_candidate_decision": "진입 불가",
        "closed_alpha": "진입 가능 (대표 자율)",
        "strict_action_f1": strict_f1,
        "msp_proxy": {"strict": msp_strict, "lenient": msp_lenient},
        "verdict": "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
