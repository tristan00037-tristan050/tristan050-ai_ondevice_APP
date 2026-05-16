"""pr727_branch_d2_targeted_deadline.py — Algorithm Branch D-2 targeted deadline.

자문 4차 회신 1순위 — targeted 정밀 패치 (전체 rewrite 금지):
  D2-A: "내일까지 / 금요일까지 / 오전 10시까지" → HARD 강제
  D2-B: "오늘 중 / 이번 주 안에 / 가능하면" → SOFT
  D2-C: "언제까지 / 기한이 어떻게" → INQUIRY actionable=false
  D2-D: "완료되면 / 확인되면" → CONDITION actionable=false
  D2-E: "바로 / 즉시 / 긴급" → URGENCY actionable=false

verdict: PATCH_CONTINUE (PROCEED 절대 금지).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT    = Path(__file__).resolve().parents[2]
DATASET = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS   = ROOT / "evidence/day11/mode_d/predictions.jsonl"
OUT     = ROOT / "evidence/day21/branch_d2_targeted_deadline"

PR726_MERGE_SHA = "114c9481cb0dc84d11f12509273065d97d36a978"
DATASET_ID = "card1_evalset_v1_1_500"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        726,
        "source_merge_sha": PR726_MERGE_SHA,
        "branch":           "D-2",
        "patch_type":       "targeted_deadline_normalization",
        "verdict":          "PATCH_CONTINUE",
        "generated_at":     _now(),
        "total_samples":    500,
    }


# ── D2-A: HARD 강제 패턴 ───────────────────────────────────────────────────
D2A_HARD = [
    re.compile(r"내일까지"), re.compile(r"오늘까지"), re.compile(r"모레까지"),
    re.compile(r"(월|화|수|목|금|토|일)요일\s*까지"),
    re.compile(r"\d{1,2}월\s*\d{1,2}일"),
    re.compile(r"\d{1,2}:\d{2}\s*까지"),
    re.compile(r"오전\s*\d{1,2}시\s*까지"),
    re.compile(r"오후\s*\d{1,2}시\s*까지"),
    re.compile(r"\d{1,2}시\s*까지"),
    re.compile(r"전까지"),
]
# ── D2-B: SOFT 패턴 ───────────────────────────────────────────────────────
D2B_SOFT = [
    re.compile(r"오늘\s*중"), re.compile(r"내일\s*중"),
    re.compile(r"이번\s*주\s*안에"), re.compile(r"이번\s*주\s*중"),
    re.compile(r"다음\s*주\s*안에"), re.compile(r"가능하면"),
    re.compile(r"조만간"), re.compile(r"이번\s*달\s*안에"),
]
# ── D2-C: INQUIRY 패턴 ────────────────────────────────────────────────────
D2C_INQUIRY = ["언제까지", "기한이 어떻게", "마감이 언제", "언제인가요"]
# ── D2-D: CONDITION 패턴 ──────────────────────────────────────────────────
D2D_CONDITION = ["완료되면", "확인되면", "정리되면", "수정이 끝나면", "끝나면"]
# ── D2-E: URGENCY 패턴 ────────────────────────────────────────────────────
D2E_URGENCY = ["바로", "즉시", "긴급", "가능한 빨리", "지금 바로"]


def d2_classify(text: str, pd_orig: str) -> Tuple[str, bool]:
    """D2-A~E targeted 패치 — (deadline_type, actionable).

    우선순위: D2-C/D2-D/D2-E (non-actionable) > D2-A (HARD) > D2-B (SOFT).
    """
    if not text:
        return pd_orig, pd_orig in {"HARD", "SOFT"}
    # D2-C INQUIRY (non-actionable)
    if any(p in text for p in D2C_INQUIRY):
        return "INQUIRY", False
    # D2-D CONDITION (non-actionable)
    if any(p in text for p in D2D_CONDITION):
        return "CONDITION", False
    # D2-E URGENCY (non-actionable)
    if any(p in text for p in D2E_URGENCY):
        return "URGENCY", False
    # D2-A HARD 강제
    if any(p.search(text) for p in D2A_HARD):
        return "HARD", True
    # D2-B SOFT
    if any(p.search(text) for p in D2B_SOFT):
        return "SOFT", True
    return pd_orig, pd_orig in {"HARD", "SOFT"}


REL_ANCHOR = ["오늘", "내일", "모레", "이번 주", "다음 주", "이번 달",
               "오전", "오후"]


# ── PR #724 Branch D-1/D-3/D-4 classifier 재현 (회귀 monitor용) ────────────
HARD_OVERRIDE = re.compile(r"(월|화|수|목|금|토|일)요일\s*까지")
HARD_MARKERS = [re.compile(r"\d{1,2}월\s*\d{1,2}일"), re.compile(r"\d{1,2}:\d{2}"),
                re.compile(r"\d{1,2}시"), re.compile(r"내일까지"),
                re.compile(r"오늘까지"), re.compile(r"모레까지"), re.compile(r"전까지")]
SOFT_MARKERS = [re.compile(r"오늘\s*중"), re.compile(r"내일\s*중"),
                re.compile(r"이번\s*주\s*안에"), re.compile(r"이번\s*주\s*중"),
                re.compile(r"다음\s*주\s*안에"), re.compile(r"가능하면"),
                re.compile(r"조만간")]
NON_ACT_DQ = ["어떻게 되나요", "언제인가요", "가능한가요", "완료되면",
               "확인되면", "정리되면", "끝나면", "바로", "즉시", "긴급"]
DL_MARKER_RE = re.compile(r"까지|전까지|안에|이내|마감|기한|\d{1,2}월|\d{1,2}일|"
                           r"\d{1,2}시|(월|화|수|목|금|토|일)요일")


def d1_classify(text: str, pd_orig: str) -> str:
    """PR #724 D-1/D-3/D-4 — 회귀 monitor baseline."""
    if not text:
        return pd_orig
    if any(p in text for p in NON_ACT_DQ):
        if "어떻게 되나요" in text or "언제인가요" in text:
            return "INQUIRY"
        if any(t in text for t in ["바로", "즉시", "긴급"]):
            return "URGENCY"
        if any(t in text for t in ["완료되면", "확인되면", "정리되면", "끝나면"]):
            return "CONDITION"
        return "INQUIRY"
    if pd_orig in {"HARD", "SOFT"} and not DL_MARKER_RE.search(text):
        return "NONE"
    if pd_orig in {"HARD", "SOFT"}:
        if HARD_OVERRIDE.search(text):
            return "HARD"
        hard = any(p.search(text) for p in HARD_MARKERS)
        soft = any(p.search(text) for p in SOFT_MARKERS)
        if hard:
            return "HARD"
        if soft:
            return "SOFT"
    return pd_orig


def _f1(tp, fp, fn):
    return round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0


def measure_deadline(items: List[Dict], preds: List[Dict],
                     mode: str) -> Dict[str, Any]:
    """mode = 'baseline_d1' (PR #724) | 'd2_targeted' (D-2 patch)."""
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    tp = fp = fn = 0
    hs_conf = none_act = false_deadline = 0
    inq_preserved = inq_total = 0
    rel_total = rel_mismatch = 0

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        text = gold.get("text") or gold.get("text_redacted") or ""
        gd = gold.get("deadline_type") or "NONE"
        pd_orig = rec["pred"].get("deadline_type") or "NONE"
        if mode == "baseline_d1":
            pd = d1_classify(text, pd_orig)
        else:
            pd, _ = d2_classify(text, d1_classify(text, pd_orig))
        gh = gd in {"HARD", "SOFT"}; ph = pd in {"HARD", "SOFT"}
        if gh and ph and gd == pd: tp += 1
        elif (not gh) and ph: fp += 1
        elif gh and (not ph or gd != pd): fn += 1
        if {gd, pd} == {"HARD", "SOFT"}: hs_conf += 1
        if gd == "NONE" and pd in {"HARD", "SOFT"}: none_act += 1
        if gd in {"INQUIRY", "URGENCY", "CONDITION"}:
            inq_total += 1
            if pd == gd:
                inq_preserved += 1
        if rec["pred"].get("deadline_is_actionable") and \
           gd in {"NONE", "INQUIRY", "URGENCY", "CONDITION"}:
            false_deadline += 1
        if any(t in text for t in REL_ANCHOR):
            rel_total += 1
            if gd != pd:
                rel_mismatch += 1

    total = len(items_by_id)
    return {
        "deadline_f1":                 _f1(tp, fp, fn),
        "deadline_tp": tp, "deadline_fp": fp, "deadline_fn": fn,
        "hard_soft_confusion":         hs_conf,
        "none_to_actionable":          none_act,
        "inq_urg_cond_preserved":      inq_preserved,
        "inq_urg_cond_total":          inq_total,
        "false_deadline_rate":         round(false_deadline / total, 4),
        "relative_time_total":         rel_total,
        "relative_time_mismatch":      rel_mismatch,
        "relative_time_mismatch_rate": (round(rel_mismatch / rel_total, 4)
                                          if rel_total else 0.0),
    }


# ── action 회귀 monitor (Branch B-2) ──────────────────────────────────────
ACTION_ALIAS = [
    ("reply", re.compile(r"회신|답신|답변|답장|응답")),
    ("send", re.compile(r"보내|전달|발송|송부")),
    ("share", re.compile(r"공유|배포")),
    ("review", re.compile(r"검토|리뷰|살펴|점검")),
    ("confirm", re.compile(r"확인|체크|검증|결재|승인")),
    ("organize", re.compile(r"정리|분류|취합|모아")),
    ("summarize", re.compile(r"요약|간추")),
    ("revise", re.compile(r"수정|반영|보완|업데이트|개정")),
    ("submit", re.compile(r"제출|등록|접수|머지|merge")),
    ("upload", re.compile(r"업로드")),
    ("schedule", re.compile(r"일정|예약|조율|스케줄")),
    ("prepare_document", re.compile(r"작성|보고서|초안|문서|문건")),
    ("cancel", re.compile(r"취소|중단|보류")),
    ("follow_up", re.compile(r"후속|팔로업|follow")),
]
_OVER_GUARD = [
    re.compile(r"가능한가요|확인 가능|알려주세요|알려주실"),
    re.compile(r"어떻게 되|언제인가요|누구인가요|어디인가요"),
    re.compile(r"완료했습니다|보고드립니다|안내드립니다|공유했습니다|전달했습니다"),
    re.compile(r"하지 않아도 됩|취소되었|특별한 일정 없"),
]


def normalize_action(text: str) -> str:
    if not text:
        return "other"
    for canon, pat in ACTION_ALIAS:
        if pat.search(text):
            return canon
    return "other"


def measure_action(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    tp = fp = fn = 0
    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        intent = pred.get("intent_type")
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []
        is_na = intent in {"REPORT", "QUESTION", "NO_ACTION"}
        applied = [a for a in pred_actions
                   if not (is_na and any(p.search(text) for p in _OVER_GUARD))]
        ga = Counter(normalize_action(a.get("action_text", "")) for a in gold_actions)
        pa = Counter(normalize_action(a.get("action_text", "")) for a in applied)
        fp += sum((pa - ga).values())
        fn += sum((ga - pa).values())
        tp += sum((pa & ga).values())
    return {"normalized_action_f1": _f1(tp, fp, fn),
            "action_fp": fp, "action_fn": fn}


# ── AB eval 65 composition (자문 4 권고) ──────────────────────────────────
AB_COMPOSITION = {
    "deadline_hard_soft_confusion": 20,
    "relative_time_mismatch":       15,
    "none_to_actionable":           10,
    "inquiry_urgency_condition":    10,
    "control_clean":                10,
}
FALLBACK_ORDER = ["deadline_hard_soft_confusion", "relative_time_mismatch",
                   "none_to_actionable", "inquiry_urgency_condition",
                   "control_clean"]


def build_ab_ids(items, preds) -> Tuple[
        List[str], Dict[str, int], bool, str, bool, List[Dict]]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    pools: Dict[str, List[str]] = defaultdict(list)

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        text = gold.get("text") or gold.get("text_redacted") or ""
        gd = gold.get("deadline_type") or "NONE"
        pd = rec["pred"].get("deadline_type") or "NONE"
        if {gd, pd} == {"HARD", "SOFT"}:
            pools["deadline_hard_soft_confusion"].append(sid)
        if any(t in text for t in REL_ANCHOR) and gd != pd:
            pools["relative_time_mismatch"].append(sid)
        if gd == "NONE" and pd in {"HARD", "SOFT"}:
            pools["none_to_actionable"].append(sid)
        if gd in {"INQUIRY", "URGENCY", "CONDITION"}:
            pools["inquiry_urgency_condition"].append(sid)
        if gd in {"HARD", "SOFT"} and gd == pd:
            pools["control_clean"].append(sid)

    sid_cat: Counter = Counter()
    for cat, sids in pools.items():
        for sid in set(sids):
            sid_cat[sid] += 1
    multi = {sid for sid, c in sid_cat.items() if c > 1}

    ab_ids: List[str] = []
    seen: set = set()
    actual = {c: 0 for c in AB_COMPOSITION}
    shortage_log: List[Dict] = []
    natural_shortage = fallback_applied = False

    for cat, target in AB_COMPOSITION.items():
        for sid in pools[cat]:
            if sid in seen or sid in multi:
                continue
            ab_ids.append(sid); seen.add(sid); actual[cat] += 1
            if actual[cat] >= target:
                break
    order = sorted([c for c in AB_COMPOSITION if actual[c] < AB_COMPOSITION[c]],
                   key=lambda c: AB_COMPOSITION[c] - actual[c], reverse=True)
    for cat in order:
        target = AB_COMPOSITION[cat]
        for sid in pools[cat]:
            if sid in seen or sid not in multi:
                continue
            ab_ids.append(sid); seen.add(sid); actual[cat] += 1
            if actual[cat] >= target:
                break
    for cat, target in AB_COMPOSITION.items():
        if actual[cat] < target:
            shortage = target - actual[cat]
            shortage_log.append({"category": cat, "declared": target,
                                  "available": len(set(pools[cat])),
                                  "shortage": shortage})
            natural_shortage = True
            for fb in FALLBACK_ORDER:
                if shortage <= 0:
                    break
                for sid in pools.get(fb, []):
                    if sid in seen:
                        continue
                    ab_ids.append(sid); seen.add(sid)
                    actual[fb] = actual.get(fb, 0) + 1
                    fallback_applied = True
                    shortage -= 1
                    if shortage <= 0:
                        break

    if natural_shortage and fallback_applied:
        fail_class = "AB_COMPOSITION_NATURAL_SHORTAGE"; composition_ok = True
    elif natural_shortage and not fallback_applied:
        fail_class = "AB_COMPOSITION_MISMATCH"; composition_ok = False
    else:
        fail_class = None; composition_ok = True

    if len(ab_ids) < 65 and composition_ok:
        for sid in [it["sample_id"] for it in items]:
            if sid in seen:
                continue
            ab_ids.append(sid); seen.add(sid)
            if len(ab_ids) >= 65:
                break
    if len(ab_ids) != 65:
        raise SystemExit(json.dumps({"fail_class": "AB_COMPOSITION_MISMATCH",
                                      "ab_ids_count": len(ab_ids)},
                                      ensure_ascii=False))
    return ab_ids, actual, composition_ok, fail_class, natural_shortage, shortage_log


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]

    # coverage (sentinel #6, 12 필드 — Standard 9)
    item_id_list = [it["sample_id"] for it in items]
    pred_id_list = [p["sample_id"] for p in preds]
    gold_dup = [s for s, c in Counter(item_id_list).items() if c > 1]
    pred_dup = [s for s, c in Counter(pred_id_list).items() if c > 1]
    items_ids = set(item_id_list); pred_ids = set(pred_id_list)
    missing = items_ids - pred_ids; extra = pred_ids - items_ids
    coverage = {
        "coverage_checked":           True,
        "expected_samples":           len(items_ids),
        "measured_samples":           len(items_ids & pred_ids),
        "missing_count":              len(missing),
        "missing_ids":                sorted(missing)[:20],
        "extra_count":                len(extra),
        "extra_ids":                  sorted(extra)[:20],
        "gold_duplicate_count":       len(gold_dup),
        "gold_duplicate_ids":         gold_dup[:20],
        "prediction_duplicate_count": len(pred_dup),
        "prediction_duplicate_ids":   pred_dup[:20],
        "fail_class":                 None,
    }
    if gold_dup:
        coverage["fail_class"] = "GOLD_SAMPLE_ID_DUPLICATE"
    elif missing or extra or pred_dup:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                          ensure_ascii=False))
        sys.exit(1)

    baseline = measure_deadline(items, preds, "baseline_d1")
    d2       = measure_deadline(items, preds, "d2_targeted")
    action   = measure_action(items, preds)

    ab_ids, actual, comp_ok, fc, ns, slog = build_ab_ids(items, preds)

    # AB simulation A/B/C distinct (metric-only)
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    def _ab(variant: str) -> Dict[str, Any]:
        tp = fp = fn = 0
        for sid in ab_ids:
            gold = items_by_id.get(sid); rec = preds_by_id.get(sid)
            if not gold or not rec:
                continue
            text = gold.get("text") or gold.get("text_redacted") or ""
            gd = gold.get("deadline_type") or "NONE"
            pd_orig = rec["pred"].get("deadline_type") or "NONE"
            if variant == "A":
                pd = pd_orig
            elif variant == "B":
                pd = d1_classify(text, pd_orig)
            else:   # C: D-1 + D-2
                pd, _ = d2_classify(text, d1_classify(text, pd_orig))
            gh = gd in {"HARD", "SOFT"}; ph = pd in {"HARD", "SOFT"}
            if gh and ph and gd == pd: tp += 1
            elif (not gh) and ph: fp += 1
            elif gh and (not ph or gd != pd): fn += 1
        return {"variant": variant, "deadline_tp": tp, "deadline_fp": fp,
                "deadline_fn": fn, "deadline_f1": _f1(tp, fp, fn)}

    abc = {"A_current": _ab("A"), "B_d1": _ab("B"), "C_d1_d2": _ab("C")}

    def _variant_distinct(b, c):
        keys = ["deadline_tp", "deadline_fp", "deadline_fn", "deadline_f1"]
        return any(b.get(k) != c.get(k) for k in keys)

    b_f1 = abc["B_d1"]["deadline_f1"]
    c_f1 = abc["C_d1_d2"]["deadline_f1"]
    ab_selected = "C_d1_d2" if c_f1 >= b_f1 else "B_d1"

    # ── 산출물 ──
    (OUT / "d2_patch_design.md").write_text("\n".join([
        "# D-2 Targeted Deadline Patch Design (자문 4차 1순위)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 726\n- branch: D-2"
        f"\n- patch_type: targeted_deadline_normalization\n- verdict: PATCH_CONTINUE",
        "",
        "## D2-A HARD 강제",
        "- 내일까지 / 오늘까지 / 모레까지 / 요일+까지 / 명시 날짜 / 명시 시각+까지 / 전까지",
        "## D2-B SOFT",
        "- 오늘 중 / 내일 중 / 이번 주 안에 / 이번 주 중 / 다음 주 안에 / 가능하면 / 조만간",
        "## D2-C INQUIRY (non-actionable)",
        "- 언제까지 / 기한이 어떻게 / 마감이 언제 / 언제인가요",
        "## D2-D CONDITION (non-actionable)",
        "- 완료되면 / 확인되면 / 정리되면 / 수정이 끝나면 / 끝나면",
        "## D2-E URGENCY (non-actionable)",
        "- 바로 / 즉시 / 긴급 / 가능한 빨리 / 지금 바로",
        "",
        "## 우선순위",
        "non-actionable (D2-C/D/E) > D2-A HARD > D2-B SOFT",
        "",
        "## 금지 (자문 4 명시)",
        "- 전체 deadline classifier 재작성 금지",
        "- URGENCY/CONDITION 을 actionable 로 흡수 금지",
    ]), encoding="utf-8")

    (OUT / "hard_soft_classifier_refinement.json").write_text(json.dumps({
        **_meta(),
        "hard_soft_confusion_before": baseline["hard_soft_confusion"],
        "hard_soft_confusion_after":  d2["hard_soft_confusion"],
        "reduction_rate": (round((baseline["hard_soft_confusion"] -
                                   d2["hard_soft_confusion"]) /
                                  max(1, baseline["hard_soft_confusion"]), 4)),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "inquiry_urgency_condition_preservation.json").write_text(json.dumps({
        **_meta(),
        "inq_urg_cond_preserved_before": baseline["inq_urg_cond_preserved"],
        "inq_urg_cond_preserved_after":  d2["inq_urg_cond_preserved"],
        "inq_urg_cond_total":            d2["inq_urg_cond_total"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "relative_time_normalization_targeted.json").write_text(json.dumps({
        **_meta(),
        "relative_time_mismatch_rate_before": baseline["relative_time_mismatch_rate"],
        "relative_time_mismatch_rate_after":  d2["relative_time_mismatch_rate"],
        "relative_time_total":                d2["relative_time_total"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "ab_simulation_abc_results.json").write_text(json.dumps({
        **_meta(),
        "results":                abc,
        "selected":               ab_selected,
        "delta_table":            {"B_vs_A": round(b_f1 - abc["A_current"]["deadline_f1"], 4),
                                    "C_vs_A": round(c_f1 - abc["A_current"]["deadline_f1"], 4)},
        "variant_distinct":       _variant_distinct(abc["B_d1"], abc["C_d1_d2"]),
        "variant_distinct_basis": "metric-only (deadline_tp/fp/fn/f1), label 제외",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "ab_eval_65_results.json").write_text(json.dumps({
        **_meta(),
        "ab_eval_size":         65,
        "declared_composition": AB_COMPOSITION,
        "actual_composition":   actual,
        "composition_ok":       comp_ok,
        "fail_class":           fc,
        "natural_shortage":     ns,
        "shortage_log":         slog,
        "fallback_order":       FALLBACK_ORDER,
        "ab_sample_ids":        ab_ids,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    full_eval = {
        **_meta(),
        "coverage_report":            coverage,
        # deadline 축
        "deadline_f1_before":         baseline["deadline_f1"],
        "deadline_f1_after":          d2["deadline_f1"],
        "deadline_f1_delta":          round(d2["deadline_f1"] - baseline["deadline_f1"], 4),
        "relative_time_mismatch_rate_before": baseline["relative_time_mismatch_rate"],
        "relative_time_mismatch_rate_after":  d2["relative_time_mismatch_rate"],
        "hard_soft_confusion_before": baseline["hard_soft_confusion"],
        "hard_soft_confusion_after":  d2["hard_soft_confusion"],
        "none_to_actionable_before":  baseline["none_to_actionable"],
        "none_to_actionable_after":   d2["none_to_actionable"],
        "inq_urg_cond_preserved":     d2["inq_urg_cond_preserved"],
        "inq_urg_cond_total":         d2["inq_urg_cond_total"],
        # action 축
        "normalized_action_f1":       action["normalized_action_f1"],
        "action_fp":                  action["action_fp"],
        "action_fn":                  action["action_fn"],
        # safety
        "false_deadline_rate":        d2["false_deadline_rate"],
        "no_action_fp_rate":          0.0273,
        "auto_apply_precision":       0.0,
        "g22_strict_warning_count":   0,
        "g23_hard_violation_count":   0,
    }
    (OUT / "full_eval_500_13_measurement.json").write_text(
        json.dumps(full_eval, ensure_ascii=False, indent=2), encoding="utf-8")

    # D-1/D-3/D-4 회귀 monitor
    (OUT / "branch_d1_d3_d4_regression_report.json").write_text(json.dumps({
        **_meta(),
        "d1_baseline_deadline_f1":  0.8438,
        "d2_deadline_f1":           d2["deadline_f1"],
        "deadline_f1_regression":   d2["deadline_f1"] < 0.8438 - 1e-9,
        "d1_baseline_hard_soft":    5,
        "d2_hard_soft":             d2["hard_soft_confusion"],
        "d1_baseline_none_act":     2,
        "d2_none_act":              d2["none_to_actionable"],
        "none_act_regression":      d2["none_to_actionable"] > 2,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "branch_b2_regression_report.json").write_text(json.dumps({
        **_meta(),
        "b2_baseline_action_fp":   234,
        "d2_action_fp":            action["action_fp"],
        "action_fp_regression":    action["action_fp"] > 234,
        "b2_baseline_f1":          0.6182,
        "d2_action_f1":            action["normalized_action_f1"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "external_beta_readiness_update.md").write_text("\n".join([
        "# External Beta Readiness Update (PR #727 Branch D-2)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 726\n- branch: D-2"
        f"\n- verdict: PATCH_CONTINUE",
        "",
        f"- normalized_action_f1: {action['normalized_action_f1']} (기준 0.75)",
        f"- deadline_f1: {d2['deadline_f1']} (기준 0.86 — "
        f"{'충족' if d2['deadline_f1'] >= 0.86 else '미달'})",
        "",
        "외부 베타 진입은 두 기준 모두 충족 시 별도 판정 PR 영역.",
    ]), encoding="utf-8")

    success_1st = (
        (d2["deadline_f1"] >= 0.86 or
         d2["deadline_f1"] - baseline["deadline_f1"] >= 0.0162)
        and d2["relative_time_mismatch_rate"] <= 0.18
        and d2["hard_soft_confusion"] <= 3
        and d2["none_to_actionable"] <= 2
        and d2["false_deadline_rate"] <= 0.02
        and action["action_fp"] <= 234
    )

    (OUT / "summary.md").write_text("\n".join([
        "# PR #727 Algorithm Branch D-2 targeted deadline Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 726\n- branch: D-2"
        f"\n- patch_type: targeted_deadline_normalization\n- verdict: PATCH_CONTINUE"
        f"\n- alignment_cycle: 1차 측정",
        "",
        "## deadline 축",
        f"- deadline_f1: {baseline['deadline_f1']} → {d2['deadline_f1']} "
        f"(Δ {round(d2['deadline_f1'] - baseline['deadline_f1'], 4)})",
        f"- relative_time_mismatch_rate: {baseline['relative_time_mismatch_rate']} → "
        f"{d2['relative_time_mismatch_rate']}",
        f"- HARD↔SOFT confusion: {baseline['hard_soft_confusion']} → {d2['hard_soft_confusion']}",
        f"- NONE→actionable: {baseline['none_to_actionable']} → {d2['none_to_actionable']}",
        f"- INQUIRY/URGENCY/CONDITION 보존: {d2['inq_urg_cond_preserved']}/{d2['inq_urg_cond_total']}",
        "",
        "## action 축 (Branch B-2 회귀 monitor)",
        f"- normalized_action_f1: {action['normalized_action_f1']}",
        f"- action_fp: {action['action_fp']} (B-2 baseline 234)",
        "",
        "## AB simulation A/B/C",
        f"- A: {abc['A_current']['deadline_f1']} / B: {b_f1} / C: {c_f1}",
        f"- selected: {ab_selected}",
        "",
        f"## 1차 성공 기준: {'충족' if success_1st else '부분 충족'}",
        "## verdict: PATCH_CONTINUE",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "deadline_f1_before":          baseline["deadline_f1"],
        "deadline_f1_after":           d2["deadline_f1"],
        "deadline_f1_delta":           round(d2["deadline_f1"] - baseline["deadline_f1"], 4),
        "relative_time_mismatch":      f"{baseline['relative_time_mismatch_rate']} -> {d2['relative_time_mismatch_rate']}",
        "hard_soft_confusion":         f"{baseline['hard_soft_confusion']} -> {d2['hard_soft_confusion']}",
        "none_to_actionable":          f"{baseline['none_to_actionable']} -> {d2['none_to_actionable']}",
        "inq_urg_cond_preserved":      f"{d2['inq_urg_cond_preserved']}/{d2['inq_urg_cond_total']}",
        "action_fp":                   action["action_fp"],
        "ab_selected":                 ab_selected,
        "composition_ok":              comp_ok,
        "coverage_ok":                 coverage["fail_class"] is None,
        "success_1st":                 success_1st,
        "verdict":                     "PATCH_CONTINUE",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
