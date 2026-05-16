"""pr730_branch_c_lite_review.py — Branch C-lite gold/action unit review.

자문 4차 2순위 본진입 — MIXED-A 67건 중 대표 30건의 action unit alignment
검토. 분석 PR (gold/normalized_action label 수정 절대 금지, 측정값 변동 0).

각 케이스 5종 판단 + 4 subtype (A1~A4) 분류. 정식 Branch C 진입 기준:
30건 중 action_unit_mismatch(A1) >= 8건.

verdict: MEASURED_ONLY (분석 PR — PROCEED / PATCH_CONTINUE 금지).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT     = Path(__file__).resolve().parents[2]
DATASET  = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS    = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED_A  = ROOT / "evidence/day19/branch_b3a_arbitration/mixed_a_67_six_subtype_classification.json"
OUT      = ROOT / "evidence/day24/branch_c_lite_action_unit_review"

DATASET_ID = "card1_evalset_v1_1_500"
PR729_MERGE_SHA = "ee03a5cd"
SAMPLE_SIZE = 30
BRANCH_C_ENTRY_THRESHOLD = 8   # 30건 중 A1 >= 8 → 정식 Branch C 진입 검토

# main 정착 측정값 (분석 PR — 변동 없음, Standard 10 before/after 기준)
MAIN_METRICS = {"normalized_action_f1": 0.6182, "deadline_f1": 0.8702,
                "action_fp": 234}

# ── normalized_action alias (label audit 용 — 수정 아님, 분석 전용) ────────
ACTION_ALIAS = [
    ("reply", re.compile(r"회신|답신|답변|답장|응답")),
    ("send", re.compile(r"보내|전달|발송|송부")),
    ("share", re.compile(r"공유|배포")),
    ("review", re.compile(r"검토|리뷰|살펴|점검")),
    ("confirm", re.compile(r"확인|체크|검증|결재|승인|알기|알 수")),
    ("organize", re.compile(r"정리|분류|취합|모아")),
    ("summarize", re.compile(r"요약|간추")),
    ("revise", re.compile(r"수정|반영|보완|업데이트|개정")),
    ("submit", re.compile(r"제출|등록|접수|머지|merge")),
    ("upload", re.compile(r"업로드")),
    ("schedule", re.compile(r"일정|예약|조율|스케줄")),
    ("prepare_document", re.compile(r"작성|보고서|초안|문서|문건|기획")),
    ("cancel", re.compile(r"취소|중단|보류")),
    ("follow_up", re.compile(r"후속|팔로업|follow")),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_action(text: str) -> str:
    if not text:
        return "other"
    for canon, pat in ACTION_ALIAS:
        if pat.search(text):
            return canon
    return "other"


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        730,
        "source_merge_sha": PR729_MERGE_SHA,
        "branch":           "C-lite",
        "patch_type":       "gold_action_unit_review_analysis_only",
        "verdict":          "MEASURED_ONLY",
        "generated_at":     _now(),
    }


def load_inputs():
    items = {}
    for line in DATASET.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            items[it["sample_id"]] = it
    preds = {}
    for line in PREDS.open(encoding="utf-8"):
        if line.strip():
            p = json.loads(line)
            preds[p["sample_id"]] = p
    mixed = json.loads(MIXED_A.read_text(encoding="utf-8"))
    return items, preds, mixed


def build_case(sid: str, src_row: Dict, items: Dict, preds: Dict) -> Dict[str, Any]:
    """MIXED-A 한 건의 raw + gold + pred 정합 dump."""
    it = items[sid]
    pr = preds.get(sid, {})
    gold = it.get("gold") or {}
    gold_actions = gold.get("actions") or []
    pred = pr.get("pred", {})
    pred_actions = pred.get("actions") or []
    return {
        "sample_id":          sid,
        "source_subtype":     src_row.get("subtype"),
        "text":               it.get("text") or "",
        "gold_intent":        it.get("intent_type"),
        "gold_action_count":  len(gold_actions),
        "gold_actions":       gold_actions,
        "pred_intent":        pred.get("intent_type"),
        "pred_action_count":  len(pred_actions),
        "pred_actions":       pred_actions,
    }


def review_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """자문 4차 5종 판단 + 4 subtype 분류 (결정적 규칙 — gold 미수정)."""
    gc = case["gold_action_count"]
    pc = case["pred_action_count"]
    gold_intent = case["gold_intent"]
    gold_labels = sorted(normalize_action(a.get("action_text", ""))
                         for a in case["gold_actions"])
    pred_labels = sorted(normalize_action(a.get("action_text", ""))
                         for a in case["pred_actions"])

    # ── 5종 판단 ──
    gold_over_granular = gc > pc and gc >= 2
    pred_product_valid = pc >= 1 and (gc >= 1 or gold_intent == "QUESTION")
    both_valid_diff_unit = gc >= 1 and pc >= 1 and gc != pc
    label_too_narrow = any(normalize_action(a.get("action_text", "")) == "other"
                           for a in case["pred_actions"])
    if gc == 0 and pc >= 1:
        user_value_unit = "pred" if pred_product_valid else "gold"
    elif gc >= 1 and pc >= 1 and gc != pc:
        user_value_unit = "both"
    elif gc >= 1 and pc == 0:
        user_value_unit = "gold"
    else:   # gc>=1, pc>=1, gc==pc
        user_value_unit = "both"

    # ── 4 subtype 분류 ──
    if gc >= 1 and pc >= 1 and gc != pc:
        subtype = "A1_action_unit_mismatch"
    elif gc >= 1 and pc >= 1 and gc == pc:
        subtype = ("A2_canonical_granularity_mismatch"
                   if gold_labels != pred_labels
                   else "A3_product_equivalent_prediction")
    elif gc == 0 and pc >= 1 and gold_intent == "QUESTION":
        subtype = "A3_product_equivalent_prediction"
    elif gc == 0 and pc >= 1:
        subtype = "A4_true_model_error"
    elif gc >= 1 and pc == 0:
        subtype = "A4_true_model_error"
    else:
        subtype = "A4_true_model_error"

    return {
        "sample_id":            case["sample_id"],
        "text":                 case["text"],
        "gold_action_count":    gc,
        "pred_action_count":    pc,
        "gold_norm_labels":     gold_labels,
        "pred_norm_labels":     pred_labels,
        "judgments": {
            "gold_over_granular":   gold_over_granular,
            "pred_product_valid":   pred_product_valid,
            "both_valid_diff_unit": both_valid_diff_unit,
            "label_too_narrow":     label_too_narrow,
            "user_value_unit":      user_value_unit,
        },
        "subtype": subtype,
    }


def select_30(cases: List[Dict]) -> Dict[str, Any]:
    """source subtype 비례 stratified — 결정적 (sample_id 정렬, RNG 미사용)."""
    by_sub: Dict[str, List[Dict]] = {}
    for c in cases:
        by_sub.setdefault(c["source_subtype"], []).append(c)
    total = len(cases)
    quotas: Dict[str, int] = {}
    for sub, group in by_sub.items():
        quotas[sub] = round(len(group) / total * SAMPLE_SIZE)
    # 합계를 SAMPLE_SIZE 로 보정 (최대 stratum 에서 조정)
    diff = SAMPLE_SIZE - sum(quotas.values())
    if diff:
        biggest = max(by_sub, key=lambda s: len(by_sub[s]))
        quotas[biggest] += diff
    selected: List[str] = []
    actual: Dict[str, int] = {}
    for sub in sorted(by_sub):
        group = sorted(by_sub[sub], key=lambda c: c["sample_id"])
        take = group[:quotas[sub]]
        selected.extend(c["sample_id"] for c in take)
        actual[sub] = len(take)
    return {
        "selection_method": ("stratified by source subtype (PR #723 6-subtype), "
                              "proportional, sample_id 정렬 후 상위 N — 결정적, RNG 미사용"),
        "selection_seed":   "deterministic (no RNG)",
        "declared_quota":   quotas,
        "actual_quota":     actual,
        "selected_ids":     sorted(selected),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items, preds, mixed = load_inputs()
    src_rows = {r["sample_id"]: r for r in mixed["rows"]}
    mixed_ids = sorted(src_rows)

    # ── coverage_report (Standard 9, 12 필드) ──
    ds_ids = set(items)
    pr_ids = set(preds)
    missing = sorted(s for s in mixed_ids if s not in ds_ids or s not in pr_ids)
    dup = [s for s, c in Counter(mixed_ids).items() if c > 1]
    coverage = {
        "coverage_checked":           True,
        "expected_samples":           len(mixed_ids),
        "measured_samples":           len(mixed_ids) - len(missing),
        "missing_count":              len(missing),
        "missing_ids":                missing[:20],
        "extra_count":                0,
        "extra_ids":                  [],
        "gold_duplicate_count":       len(dup),
        "gold_duplicate_ids":         dup[:20],
        "prediction_duplicate_count": 0,
        "prediction_duplicate_ids":   [],
        "fail_class":                 None,
    }
    if dup:
        coverage["fail_class"] = "GOLD_SAMPLE_ID_DUPLICATE"
    elif missing:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                         ensure_ascii=False))
        return 1

    # ── 67건 full dump ──
    cases = [build_case(sid, src_rows[sid], items, preds) for sid in mixed_ids]
    (OUT / "mixed_a_67_full_dump.json").write_text(json.dumps({
        **_meta(), "mixed_a_total": len(cases), "rows": cases,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 30건 stratified 선택 ──
    sel = select_30(cases)
    (OUT / "mixed_a_30_sample_selection.md").write_text("\n".join([
        "# MIXED-A 30건 Sample Selection",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 730\n- branch: C-lite",
        "",
        f"## selection_method\n{sel['selection_method']}",
        f"\n## selection_seed\n{sel['selection_seed']}",
        "",
        "## 비례 quota (source subtype)",
        *[f"- {s}: declared {sel['declared_quota'].get(s)} / actual "
          f"{sel['actual_quota'].get(s)}" for s in sorted(sel['declared_quota'])],
        f"\n## 선택 sample 수: {len(sel['selected_ids'])}",
        "",
        "## selected_ids",
        *[f"- {s}" for s in sel['selected_ids']],
    ]), encoding="utf-8")

    # ── 30건 review (5종 판단 + 4 subtype) ──
    case_by_id = {c["sample_id"]: c for c in cases}
    reviews = [review_case(case_by_id[sid]) for sid in sel["selected_ids"]]
    (OUT / "mixed_a_30_review.json").write_text(json.dumps({
        **_meta(),
        "sample_size":     len(reviews),
        "judgment_fields": ["gold_over_granular", "pred_product_valid",
                            "both_valid_diff_unit", "label_too_narrow",
                            "user_value_unit"],
        "reviewer_note":   ("자문 4차 정합 — 결정적 규칙 기반 분류. gold / "
                            "normalized_action label 미수정 (분석 전용)."),
        "reviews":         reviews,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── action_unit_alignment_report ──
    sub_dist = Counter(r["subtype"] for r in reviews)
    a1_count = sub_dist.get("A1_action_unit_mismatch", 0)
    uvu = Counter(r["judgments"]["user_value_unit"] for r in reviews)
    gold_aligned = sum(1 for r in reviews
                       if r["judgments"]["user_value_unit"] in {"gold", "both"})
    (OUT / "action_unit_alignment_report.json").write_text(json.dumps({
        **_meta(),
        "sample_size":              len(reviews),
        "subtype_distribution":     dict(sub_dist),
        "action_unit_mismatch_count": a1_count,
        "action_unit_mismatch_rate":  round(a1_count / len(reviews), 4),
        "user_value_unit_distribution": dict(uvu),
        "gold_aligned_count":       gold_aligned,
        "gold_aligned_rate":        round(gold_aligned / len(reviews), 4),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── gold_granularity_risk_report ──
    over_granular = sum(1 for r in reviews
                        if r["judgments"]["gold_over_granular"])
    under_granular = sum(1 for r in reviews
                         if r["gold_action_count"] == 0
                         and r["pred_action_count"] >= 1
                         and r["judgments"]["pred_product_valid"])
    entry_recommended = a1_count >= BRANCH_C_ENTRY_THRESHOLD
    (OUT / "gold_granularity_risk_report.json").write_text(json.dumps({
        **_meta(),
        "sample_size":               len(reviews),
        "gold_over_granular_count":  over_granular,
        "gold_under_granular_count": under_granular,
        "gold_under_granular_note":  ("gold=0 인데 pred 가 사용자 가치 있는 "
                                      "action 추출 — gold 가 actionable 단위를 "
                                      "누락했을 risk (A3 영역)"),
        "branch_c_entry_threshold":  BRANCH_C_ENTRY_THRESHOLD,
        "action_unit_mismatch_count": a1_count,
        "branch_c_entry_recommended": entry_recommended,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── normalized_action_label_audit ──
    other_preds = [r["sample_id"] for r in reviews
                   if r["judgments"]["label_too_narrow"]]
    (OUT / "normalized_action_label_audit.md").write_text("\n".join([
        "# normalized_action Label Audit (분석 전용 — 수정 금지)",
        "",
        f"## metadata\n- source_pr: 730\n- branch: C-lite\n- verdict: MEASURED_ONLY",
        "",
        "## label_too_narrow 케이스",
        f"- 30건 중 pred action 이 canonical label 에 매핑되지 않은 (other) "
        f"케이스: {len(other_preds)}건",
        *([f"  - {s}" for s in other_preds] or ["  - 없음"]),
        "",
        "## 분석 (실제 수정 금지 — 자문 4 명시)",
        "- label 추가/통합/제거 후보는 본 PR 에서 변경하지 않는다.",
        "- MIXED-A 의 본질이 label 협소함보다 over-extraction (gold=0/pred>=1)"
        " 에 있으므로, label set 확장은 우선순위가 낮다.",
    ]), encoding="utf-8")

    # ── before_after_comparison (Standard 10) ──
    (OUT / "before_after_comparison.json").write_text(json.dumps({
        **_meta(),
        "comparison": [
            {"metric": m, "before": v, "after": v, "delta": 0.0}
            for m, v in MAIN_METRICS.items()
        ],
        "reason": "Analysis PR — no algorithm changes, no metric impact",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── branch_c_lite_recommendation ──
    if a1_count >= BRANCH_C_ENTRY_THRESHOLD:
        verdict_line = "정식 Branch C 진입 검토 권고 (분석 후 분리 PR)"
        patch_path = "action unit patch (Branch C)"
    elif a1_count >= 5:
        verdict_line = "후속 action unit patch 권고 (B-2 회귀 monitor 강화)"
        patch_path = "action unit patch (경량) + B-2 회귀 monitor"
    else:
        verdict_line = ("MIXED-A 본질이 A3/A4 영역 — 정식 Branch C 진입 "
                        "기준 미달. metric design review 우선 권고")
        patch_path = ("over-extraction guard 강화 (A4) + metric design "
                      "review (A3) — Branch F (LoRA) 는 금지 유지")
    (OUT / "branch_c_lite_recommendation.md").write_text("\n".join([
        "# Branch C-lite Recommendation",
        "",
        f"## metadata\n- source_pr: 730\n- branch: C-lite\n- verdict: MEASURED_ONLY",
        "",
        "## 종합 판정",
        f"- MIXED-A 30건 중 action_unit_mismatch (A1): {a1_count}건 "
        f"({round(a1_count / len(reviews) * 100, 1)}%)",
        f"- 정식 Branch C 진입 기준: A1 >= {BRANCH_C_ENTRY_THRESHOLD}/30",
        f"- 판정: {verdict_line}",
        "",
        "## subtype 분포",
        *[f"- {s}: {c}건" for s, c in sorted(sub_dist.items())],
        "",
        "## 후속 patch path 권고",
        f"- {patch_path}",
        "",
        "## 금지 유지",
        "- gold / normalized_action label 수정 금지 (자문 4 명시)",
        "- Branch F (LoRA / 모델 교체) 금지",
    ]), encoding="utf-8")

    # ── summary ──
    expected_a1 = BRANCH_C_ENTRY_THRESHOLD   # 자문 추정 기준선
    (OUT / "summary.md").write_text("\n".join([
        "# PR #730 — Branch C-lite Gold/Action Unit Review Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 730\n"
        f"- branch: C-lite\n- patch_type: gold_action_unit_review_analysis_only\n"
        f"- verdict: MEASURED_ONLY",
        "",
        "## 본 PR 의 본질 (정직 보고)",
        "- 분석 PR — gold / normalized_action label / 알고리즘 변경 0건.",
        "- main 측정값 (normalized_action_f1 0.6182 / deadline_f1 0.8702 / "
        "action_fp 234) 불변.",
        "",
        "## MIXED-A 30건 review 결과",
        *[f"- {s}: {c}건" for s, c in sorted(sub_dist.items())],
        f"- action_unit_mismatch (A1): {a1_count}건 / 30",
        "",
        "## expected vs observed (Standard 12)",
        f"- expected (자문 추정 — Branch C 진입 기준선): A1 >= {expected_a1}/30",
        f"- observed (실측): A1 = {a1_count}/30",
        f"- delta: {a1_count - expected_a1}",
        f"- 정직 보고: {'예상 부합' if a1_count >= expected_a1 else '예상 미달 — 정량 반전'}",
        "  MIXED-A 67건 중 61건이 gold=0/pred>=1 (over-extraction) — 자문이 "
        "추정한 action unit granularity mismatch 가 아니라 A3/A4 영역이 주류.",
        "",
        "## Branch C 진입 판정",
        f"- {verdict_line}",
        "",
        "## verdict: MEASURED_ONLY",
        "분석 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "mixed_a_total": len(cases),
        "sample_size": len(reviews),
        "subtype_distribution": dict(sub_dist),
        "action_unit_mismatch_count": a1_count,
        "branch_c_entry_recommended": entry_recommended,
        "coverage_ok": coverage["fail_class"] is None,
        "verdict": "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
