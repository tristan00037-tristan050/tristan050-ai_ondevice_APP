"""pr723_branch_d_measurement.py — Algorithm Branch D 측정 보강 (병렬).

자문 3.1/3.3 정합:
  - Branch B-2 (PR #722) 와 병렬, 영향 축 분리
  - deadline_f1 정확 측정 + 5종 혼동 카테고리 + relative time normalization 오류
  - classifier / threshold / prompt 변경 없음 (측정 PR)

verdict: MEASURED_ONLY (PATCH 적용 없음).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT    = Path(__file__).resolve().parents[2]
DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
OUT     = ROOT / "evidence/day18/branch_d_measurement"

PR720_MERGE_SHA = "e838543b44cfa03ab31893304547f7218de44b82"
PR721_MERGE_SHA = "cc0b5759ca794a08797a4ffc5bd5260608c47c1e"
DATASET_ID = "card1_evalset_v1_1_500"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        720,
        "source_merge_sha": PR720_MERGE_SHA,
        "ops_pr":           721,
        "ops_merge_sha":    PR721_MERGE_SHA,
        "branch":           "D",
        "patch_type":       "measurement_only",
        "verdict":          "MEASURED_ONLY",
        "generated_at":     _now(),
        "total_samples":    500,
    }


# ── deadline 패턴 ─────────────────────────────────────────────────────────
INQUIRY_TOKENS   = ["언제까지", "기한이 어떻게", "마감이 언제", "언제인가요", "언제죠"]
URGENCY_TOKENS   = ["지금", "즉시", "ASAP", "바로", "긴급", "가능한 빨리"]
CONDITION_TOKENS = ["완료되면", "확인되면", "수정이 끝나면", "정리되면", "끝나면"]
RELATIVE_TIME    = ["오늘", "내일", "이번 주", "다음 주", "오전", "오후",
                     "회의 전", "이번 달"]
ABSOLUTE_RE      = re.compile(r"\d{1,2}월\s*\d{1,2}일|\d{4}-\d{1,2}-\d{1,2}|"
                                r"\d{1,2}:\d{2}|\d{1,2}시")


def _deadline_pattern(text: str) -> str:
    if not text:
        return "other"
    if any(t in text for t in INQUIRY_TOKENS):   return "inquiry_pattern"
    if any(t in text for t in URGENCY_TOKENS):   return "urgency_pattern"
    if any(t in text for t in CONDITION_TOKENS): return "condition_pattern"
    if ABSOLUTE_RE.search(text):                  return "absolute_time"
    if any(t in text for t in RELATIVE_TIME):     return "relative_time"
    return "other"


# ── 1) deadline_f1 breakdown (sample 단위) ────────────────────────────────
def step1_deadline_breakdown(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    rows: List[Dict] = []
    confusion: Counter = Counter()    # (gold_type, pred_type)
    type_dist: Counter = Counter()
    actionable_match = 0
    actionable_total = 0

    tp = fp = fn = 0
    type_match = 0
    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        gd = gold.get("deadline_type") or "NONE"
        pd = pred.get("deadline_type") or "NONE"
        text = gold.get("text") or gold.get("text_redacted") or ""
        confusion[(gd, pd)] += 1
        type_dist[gd] += 1
        # F1 (HARD/SOFT 매칭)
        gh = gd in {"HARD", "SOFT"}
        ph = pd in {"HARD", "SOFT"}
        if gh and ph and gd == pd:
            tp += 1; type_match += 1
        elif (not gh) and ph:
            fp += 1
        elif gh and (not ph or gd != pd):
            fn += 1
        # actionable 정합
        gold_act = gold.get("deadline_is_actionable")
        pred_act = pred.get("deadline_is_actionable")
        actionable_total += 1
        if gold_act == pred_act:
            actionable_match += 1

        if gd != pd:
            rows.append({
                "sample_id":      sid,
                "gold_type":      gd,
                "pred_type":      pd,
                "gold_actionable": gold_act,
                "pred_actionable": pred_act,
                "pattern":        _deadline_pattern(text),
                "text_excerpt":   text[:80],
            })

    f1 = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0
    return {
        **_meta(),
        "deadline_f1":             f1,
        "deadline_tp":             tp,
        "deadline_fp":             fp,
        "deadline_fn":             fn,
        "type_match_count":        type_match,
        "type_total":              sum(type_dist.values()),
        "actionable_match_rate":   round(actionable_match / max(1, actionable_total), 4),
        "type_distribution":       dict(type_dist),
        "confusion_matrix":        {f"{g}->{p}": c for (g, p), c in confusion.items()},
        "mismatch_rows":           rows,
    }


# ── 2) INQUIRY/URGENCY/CONDITION 혼동 측정 ────────────────────────────────
def step2_confusion_breakdown(deadline_b: Dict[str, Any]) -> Dict[str, Any]:
    """5종 카테고리 혼동 비중."""
    cm = deadline_b["confusion_matrix"]
    type_total = deadline_b["type_distribution"]

    def _count(gold_t, pred_set):
        return sum(c for k, c in cm.items()
                    if k.split("->")[0] == gold_t and k.split("->")[1] in pred_set)

    inq_total      = type_total.get("INQUIRY", 0)
    urg_total      = type_total.get("URGENCY", 0)
    cond_total     = type_total.get("CONDITION", 0)
    hard_total     = type_total.get("HARD", 0)
    soft_total     = type_total.get("SOFT", 0)
    none_total     = type_total.get("NONE", 0)

    return {
        **_meta(),
        "INQUIRY_misclassified_as_HARD_or_SOFT": {
            "count":     _count("INQUIRY", {"HARD", "SOFT"}),
            "gold_total": inq_total,
            "rate":       round(_count("INQUIRY", {"HARD", "SOFT"}) / max(1, inq_total), 4),
        },
        "URGENCY_misclassified_as_SOFT": {
            "count":     _count("URGENCY", {"SOFT"}),
            "gold_total": urg_total,
            "rate":       round(_count("URGENCY", {"SOFT"}) / max(1, urg_total), 4),
        },
        "URGENCY_misclassified_as_HARD_or_SOFT": {
            "count":     _count("URGENCY", {"HARD", "SOFT"}),
            "gold_total": urg_total,
            "rate":       round(_count("URGENCY", {"HARD", "SOFT"}) / max(1, urg_total), 4),
        },
        "CONDITION_misclassified_as_HARD_or_SOFT": {
            "count":     _count("CONDITION", {"HARD", "SOFT"}),
            "gold_total": cond_total,
            "rate":       round(_count("CONDITION", {"HARD", "SOFT"}) / max(1, cond_total), 4),
        },
        "HARD_misclassified_as_SOFT": {
            "count":     _count("HARD", {"SOFT"}),
            "gold_total": hard_total,
            "rate":       round(_count("HARD", {"SOFT"}) / max(1, hard_total), 4),
        },
        "SOFT_misclassified_as_HARD": {
            "count":     _count("SOFT", {"HARD"}),
            "gold_total": soft_total,
            "rate":       round(_count("SOFT", {"HARD"}) / max(1, soft_total), 4),
        },
        "NONE_misclassified_as_actionable": {
            "count":     _count("NONE", {"HARD", "SOFT"}),
            "gold_total": none_total,
            "rate":       round(_count("NONE", {"HARD", "SOFT"}) / max(1, none_total), 4),
        },
    }


# ── 3) relative time normalization 오류 ───────────────────────────────────
def step3_relative_time_errors(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    rows: List[Dict] = []
    pattern_counter: Counter = Counter()
    rel_total = abs_total = mismatch_total = 0

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        text = gold.get("text") or gold.get("text_redacted") or ""
        pattern = _deadline_pattern(text)
        if pattern == "relative_time":
            rel_total += 1
        elif pattern == "absolute_time":
            abs_total += 1

        gd = gold.get("deadline_type") or "NONE"
        pd = (rec["pred"].get("deadline_type") or "NONE")
        gold_act = gold.get("deadline_is_actionable")
        pred_act = rec["pred"].get("deadline_is_actionable")

        # relative time 영역에서 type / actionable 불일치
        if pattern == "relative_time" and (gd != pd or gold_act != pred_act):
            mismatch_total += 1
            pattern_counter[f"{gd}->{pd}"] += 1
            rows.append({
                "sample_id":      sid,
                "pattern":        "relative_time",
                "gold_type":      gd,
                "pred_type":      pd,
                "gold_actionable": gold_act,
                "pred_actionable": pred_act,
                "text_excerpt":   text[:80],
            })

    return {
        **_meta(),
        "relative_time_total":          rel_total,
        "absolute_time_total":          abs_total,
        "relative_time_mismatch_count": mismatch_total,
        "relative_time_mismatch_rate":  (round(mismatch_total / max(1, rel_total), 4)
                                          if rel_total else 0.0),
        "top_confusion_patterns":       dict(pattern_counter.most_common(20)),
        "mismatch_rows":                rows[:50],
    }


# ── 4) Branch D quantitative readiness ────────────────────────────────────
def step4_readiness(d_breakdown: Dict, confusion: Dict, rel_time: Dict) -> Dict[str, Any]:
    enter_branch_d = (
        d_breakdown["deadline_f1"] < 0.90
        or confusion["INQUIRY_misclassified_as_HARD_or_SOFT"]["count"] > 0
        or confusion["URGENCY_misclassified_as_HARD_or_SOFT"]["count"] > 0
        or confusion["CONDITION_misclassified_as_HARD_or_SOFT"]["count"] > 0
    )
    enter_branch_d_main_pr = (
        d_breakdown["deadline_f1"] < 0.85 or
        rel_time["relative_time_mismatch_rate"] > 0.10
    )
    return {
        **_meta(),
        "deadline_f1":                  d_breakdown["deadline_f1"],
        "deadline_f1_threshold":        0.90,
        "actionable_match_rate":        d_breakdown["actionable_match_rate"],
        "relative_time_mismatch_rate":  rel_time["relative_time_mismatch_rate"],
        "enter_branch_d_assessment_pr": enter_branch_d,
        "enter_branch_d_main_pr":       enter_branch_d_main_pr,
        "next_step": (
            "Branch D 본진입 PR 권장 (deadline classifier patch)"
            if enter_branch_d_main_pr else
            "Branch D 측정 보강만 유지 (본진입 PR 보류)"
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]

    # coverage fail-closed (sentinel #6)
    items_ids = {it["sample_id"] for it in items}
    pred_ids  = {p["sample_id"] for p in preds}
    missing = items_ids - pred_ids
    extra   = pred_ids - items_ids
    dup     = [s for s, c in Counter([p["sample_id"] for p in preds]).items() if c > 1]
    coverage = {
        "coverage_checked":  True,
        "expected_samples":  len(items_ids),
        "measured_samples":  len(items_ids & pred_ids),
        "missing_count":     len(missing),
        "extra_count":       len(extra),
        "duplicate_count":   len(dup),
        "fail_class":        ("FULL_EVAL_COVERAGE_MISMATCH"
                                if (missing or extra or dup) else None),
    }
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                          ensure_ascii=False))
        sys.exit(1)

    d_breakdown = step1_deadline_breakdown(items, preds)
    confusion   = step2_confusion_breakdown(d_breakdown)
    rel_time    = step3_relative_time_errors(items, preds)
    readiness   = step4_readiness(d_breakdown, confusion, rel_time)

    # coverage_report 주입
    d_breakdown["coverage_report"] = coverage

    (OUT / "deadline_f1_breakdown.json").write_text(
        json.dumps(d_breakdown, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "inquiry_urgency_condition_confusion.json").write_text(
        json.dumps(confusion, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "relative_time_normalization_errors.json").write_text(
        json.dumps(rel_time, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "branch_d_readiness_quantitative.md").write_text("\n".join([
        "# Branch D Quantitative Readiness (PR #723 측정 결과 기준)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 720"
        f"\n- ops_pr: 721\n- branch: D\n- patch_type: measurement_only\n- verdict: MEASURED_ONLY",
        "",
        f"- deadline_f1: {readiness['deadline_f1']} (threshold {readiness['deadline_f1_threshold']})",
        f"- actionable_match_rate: {readiness['actionable_match_rate']}",
        f"- relative_time_mismatch_rate: {readiness['relative_time_mismatch_rate']}",
        f"- enter_branch_d_assessment_pr: {readiness['enter_branch_d_assessment_pr']}",
        f"- enter_branch_d_main_pr: {readiness['enter_branch_d_main_pr']}",
        f"- next_step: {readiness['next_step']}",
        "",
        "## 5종 혼동 카테고리 비중",
        *[f"- {k}: count={v['count']}, gold_total={v['gold_total']}, rate={v['rate']}"
           for k, v in confusion.items() if isinstance(v, dict)],
    ]), encoding="utf-8")

    (OUT / "summary.md").write_text("\n".join([
        "# PR #723 Algorithm Branch D measurement Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 720"
        f"\n- ops_pr: 721\n- branch: D\n- patch_type: measurement_only"
        f"\n- verdict: MEASURED_ONLY",
        "",
        "## deadline_f1 breakdown",
        f"- deadline_f1: {d_breakdown['deadline_f1']}",
        f"- tp / fp / fn: {d_breakdown['deadline_tp']} / {d_breakdown['deadline_fp']} / {d_breakdown['deadline_fn']}",
        f"- actionable_match_rate: {d_breakdown['actionable_match_rate']}",
        f"- mismatch_rows: {len(d_breakdown['mismatch_rows'])}",
        "",
        "## type_distribution",
        *[f"- {k}: {v}" for k, v in d_breakdown["type_distribution"].items()],
        "",
        "## 5종 혼동 카테고리",
        *[f"- {k}: count={v['count']}, rate={v['rate']}"
           for k, v in confusion.items() if isinstance(v, dict)],
        "",
        "## relative time normalization",
        f"- relative_time_total: {rel_time['relative_time_total']}",
        f"- mismatch_count: {rel_time['relative_time_mismatch_count']}",
        f"- mismatch_rate: {rel_time['relative_time_mismatch_rate']}",
        "",
        "## Branch D readiness",
        f"- enter_branch_d_assessment_pr: {readiness['enter_branch_d_assessment_pr']}",
        f"- enter_branch_d_main_pr: {readiness['enter_branch_d_main_pr']}",
        f"- next_step: {readiness['next_step']}",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok":                            True,
        "deadline_f1":                   d_breakdown["deadline_f1"],
        "deadline_tp_fp_fn":             [d_breakdown["deadline_tp"], d_breakdown["deadline_fp"], d_breakdown["deadline_fn"]],
        "actionable_match_rate":         d_breakdown["actionable_match_rate"],
        "INQUIRY_to_HARD_SOFT":          confusion["INQUIRY_misclassified_as_HARD_or_SOFT"]["count"],
        "URGENCY_to_HARD_SOFT":          confusion["URGENCY_misclassified_as_HARD_or_SOFT"]["count"],
        "CONDITION_to_HARD_SOFT":        confusion["CONDITION_misclassified_as_HARD_or_SOFT"]["count"],
        "HARD_to_SOFT":                  confusion["HARD_misclassified_as_SOFT"]["count"],
        "NONE_to_actionable":            confusion["NONE_misclassified_as_actionable"]["count"],
        "relative_time_mismatch_rate":   rel_time["relative_time_mismatch_rate"],
        "enter_branch_d_main_pr":        readiness["enter_branch_d_main_pr"],
        "coverage_ok":                   coverage["fail_class"] is None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
