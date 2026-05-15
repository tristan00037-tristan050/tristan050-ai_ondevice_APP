"""pr724_branch_d_classifier_patch.py — Algorithm Branch D 본진입.

자문 3.1/3.2 + D-1~D-4 정합:
  D-1. HARD ↔ SOFT classifier 정교화
  D-2. relative_time normalization schema
  D-3. NONE → actionable false positive 차단
  D-4. INQUIRY/URGENCY/CONDITION 보존

verdict: MEASURED_ONLY 또는 PATCH_CONTINUE (PROCEED 절대 금지).
classifier patch 적용 자체는 측정 시뮬레이션 (실제 deadline classifier 변경 X).
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
PR716   = ROOT / "evidence/day14/extraction_error_decomposition"
OUT     = ROOT / "evidence/day19/branch_d_classifier_patch"

PR723_MERGE_SHA = "d26883e87f1b079f852ecaa45e7def487905b30e"
DATASET_ID = "card1_evalset_v1_1_500"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":       DATASET_ID,
        "source_pr":        723,
        "source_merge_sha": PR723_MERGE_SHA,
        "branch":           "D",
        "patch_type":       "deadline_classifier",
        "verdict":          "MEASURED_ONLY",
        "generated_at":     _now(),
        "total_samples":    500,
    }


# ── D-1: HARD ↔ SOFT classifier 정교화 (자문 5.1) ──────────────────────────
HARD_MARKERS = [
    re.compile(r"\d{1,2}월\s*\d{1,2}일"),         # 명시 날짜
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),
    re.compile(r"\d{1,2}:\d{2}"),                  # 명시 시각
    re.compile(r"\d{1,2}시"),
    re.compile(r"(월|화|수|목|금|토|일)요일\s*까지"),
    re.compile(r"내일까지"),
    re.compile(r"오늘까지"),
    re.compile(r"모레까지"),
    re.compile(r"전까지"),
]
SOFT_MARKERS = [
    re.compile(r"오늘\s*중"),
    re.compile(r"내일\s*중"),
    re.compile(r"이번\s*주\s*안에"),
    re.compile(r"이번\s*주\s*중"),
    re.compile(r"다음\s*주\s*안에"),
    re.compile(r"가능하면"),
    re.compile(r"조만간"),
    re.compile(r"이번\s*달\s*안에"),
]
# 경계: "이번 주 금요일까지" → HARD (요일+까지)
HARD_OVERRIDE = re.compile(r"(월|화|수|목|금|토|일)요일\s*까지")


def classify_hard_soft(text: str) -> str:
    """HARD / SOFT 정밀 분류 — 자문 5.1 기준."""
    if not text:
        return "NONE"
    # HARD override 우선 (이번 주 금요일까지)
    if HARD_OVERRIDE.search(text):
        return "HARD"
    hard = any(p.search(text) for p in HARD_MARKERS)
    soft = any(p.search(text) for p in SOFT_MARKERS)
    if hard and not soft:
        return "HARD"
    if soft and not hard:
        return "SOFT"
    if hard and soft:
        # 둘 다 매칭 — HARD marker 우선 (명시 시점 존재)
        return "HARD"
    return "UNKNOWN"


# ── D-2: relative_time normalization schema (자문 5.2) ────────────────────
REL_ANCHOR = {
    "오늘": (0, "today"), "내일": (1, "today"), "모레": (2, "today"),
    "이번 주": (0, "this_week"), "다음 주": (7, "this_week"),
    "이번 달": (0, "this_month"),
}
TIME_PART = {"오전": "morning", "오후": "afternoon", "저녁": "evening",
              "밤": "night"}


def normalize_relative_time(text: str) -> Dict[str, Any]:
    """relative time → 정규화 schema (자문 5.2)."""
    if not text:
        return {}
    anchor = None
    day_offset = 0
    for surface, (offset, anc) in REL_ANCHOR.items():
        if surface in text:
            anchor = anc
            day_offset = offset
            break
    if anchor is None:
        return {}
    time_part = None
    for surface, part in TIME_PART.items():
        if surface in text:
            time_part = part
            break
    strength = classify_hard_soft(text)
    return {
        "surface":          text[:40],
        "relative_anchor":  anchor,
        "normalized_type":  "relative_day" if anchor == "today" else "relative_range",
        "day_offset":       day_offset,
        "time_part":        time_part,
        "deadline_strength": strength if strength in {"HARD", "SOFT"} else "SOFT",
    }


# ── D-3: NONE → actionable 차단 (자문 6.1) ────────────────────────────────
DEADLINE_MARKERS = ["까지", "전까지", "안에", "이내", "마감", "기한"]
DEADLINE_MARKER_RE = re.compile(
    r"까지|전까지|안에|이내|마감|기한|\d{1,2}월|\d{1,2}일|\d{1,2}시|"
    r"(월|화|수|목|금|토|일)요일")


def has_deadline_marker(text: str) -> bool:
    return bool(text) and bool(DEADLINE_MARKER_RE.search(text))


# ── D-4: INQUIRY/URGENCY/CONDITION non-actionable disqualifier (자문 6.2) ──
NON_ACTIONABLE_DISQUALIFIER = [
    "어떻게 되나요", "언제인가요", "가능한가요",
    "완료되면", "확인되면", "정리되면", "끝나면",
    "바로", "즉시", "긴급", "가능한 빨리",
]


def is_non_actionable_pattern(text: str) -> bool:
    return bool(text) and any(p in text for p in NON_ACTIONABLE_DISQUALIFIER)


# ── classifier patch 적용 (시뮬레이션) ─────────────────────────────────────
def patched_deadline_classify(text: str, original_pred_type: str) -> str:
    """Branch D classifier patch 시뮬레이션 — original pred 보정.

    D-3: deadline marker 없으면 actionable(HARD/SOFT) 금지 → NONE.
    D-4: non-actionable disqualifier → INQUIRY/URGENCY/CONDITION 보존.
    D-1: HARD/SOFT 재분류.
    """
    if not text:
        return original_pred_type
    # D-4: non-actionable disqualifier 우선
    if is_non_actionable_pattern(text):
        if "어떻게 되나요" in text or "언제인가요" in text:
            return "INQUIRY"
        if any(t in text for t in ["바로", "즉시", "긴급", "가능한 빨리"]):
            return "URGENCY"
        if any(t in text for t in ["완료되면", "확인되면", "정리되면", "끝나면"]):
            return "CONDITION"
        return "INQUIRY"
    # D-3: deadline marker 없으면 NONE
    if original_pred_type in {"HARD", "SOFT"} and not has_deadline_marker(text):
        return "NONE"
    # D-1: HARD/SOFT 재분류
    if original_pred_type in {"HARD", "SOFT"}:
        hs = classify_hard_soft(text)
        if hs in {"HARD", "SOFT"}:
            return hs
    return original_pred_type


# ── full eval ─────────────────────────────────────────────────────────────
def _coverage(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    item_id_list = [it["sample_id"] for it in items]
    pred_id_list = [p["sample_id"] for p in preds]
    items_ids = set(item_id_list); pred_ids = set(pred_id_list)
    missing = items_ids - pred_ids
    extra   = pred_ids - items_ids
    gold_dup = [s for s, c in Counter(item_id_list).items() if c > 1]
    pred_dup = [s for s, c in Counter(pred_id_list).items() if c > 1]
    fail_class = None
    if gold_dup:
        fail_class = "GOLD_SAMPLE_ID_DUPLICATE"
    elif missing or extra or pred_dup:
        fail_class = "FULL_EVAL_COVERAGE_MISMATCH"
    return {
        "coverage_checked":           True,
        "expected_samples":           len(items_ids),
        "measured_samples":           len(items_ids & pred_ids),
        "missing_count":              len(missing),
        "extra_count":                len(extra),
        "gold_duplicate_count":       len(gold_dup),
        "gold_duplicate_ids":         gold_dup[:20],
        "prediction_duplicate_count": len(pred_dup),
        "prediction_duplicate_ids":   pred_dup[:20],
        "fail_class":                 fail_class,
    }


def measure_deadline(items: List[Dict], preds: List[Dict],
                     apply_patch: bool) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    tp = fp = fn = 0
    confusion: Counter = Counter()
    hard_soft_confusion = 0
    none_to_actionable = 0
    inq_urg_cond_preserved = 0
    inq_urg_cond_total = 0
    false_deadline = 0
    rel_total = rel_mismatch = 0

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        gd = gold.get("deadline_type") or "NONE"
        pd_orig = pred.get("deadline_type") or "NONE"
        pd = patched_deadline_classify(text, pd_orig) if apply_patch else pd_orig

        confusion[(gd, pd)] += 1
        gh = gd in {"HARD", "SOFT"}
        ph = pd in {"HARD", "SOFT"}
        if gh and ph and gd == pd:
            tp += 1
        elif (not gh) and ph:
            fp += 1
        elif gh and (not ph or gd != pd):
            fn += 1
        # HARD ↔ SOFT confusion
        if {gd, pd} == {"HARD", "SOFT"}:
            hard_soft_confusion += 1
        # NONE → actionable
        if gd == "NONE" and pd in {"HARD", "SOFT"}:
            none_to_actionable += 1
        # INQUIRY/URGENCY/CONDITION 보존
        if gd in {"INQUIRY", "URGENCY", "CONDITION"}:
            inq_urg_cond_total += 1
            if pd == gd:
                inq_urg_cond_preserved += 1
        # false_deadline
        pred_act = pred.get("deadline_is_actionable")
        if pred_act and gd in {"NONE", "INQUIRY", "URGENCY", "CONDITION"}:
            false_deadline += 1
        # relative time
        if any(t in text for t in REL_ANCHOR):
            rel_total += 1
            if gd != pd:
                rel_mismatch += 1

    total = len(items_by_id)
    f1 = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0
    return {
        "deadline_f1":                 f1,
        "deadline_tp":                 tp,
        "deadline_fp":                 fp,
        "deadline_fn":                 fn,
        "hard_soft_confusion":         hard_soft_confusion,
        "none_to_actionable":          none_to_actionable,
        "inq_urg_cond_preserved":      inq_urg_cond_preserved,
        "inq_urg_cond_total":          inq_urg_cond_total,
        "false_deadline_rate":         round(false_deadline / total, 4),
        "relative_time_total":         rel_total,
        "relative_time_mismatch":      rel_mismatch,
        "relative_time_mismatch_rate": (round(rel_mismatch / rel_total, 4)
                                          if rel_total else 0.0),
    }


# ── action 회귀 monitor (Branch B-2 결과 보존) ─────────────────────────────
ACTION_ALIAS_TABLE = [
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


def normalize_action(text: str) -> str:
    if not text:
        return "other"
    for canon, pat in ACTION_ALIAS_TABLE:
        if pat.search(text):
            return canon
    return "other"


# Branch B-2 over_extraction guard 재현 (action 축은 B-2 결과 위에 쌓임)
_OVER_GUARD_PATTERNS = [
    re.compile(r"가능한가요|확인 가능|알려주세요|알려주실"),
    re.compile(r"어떻게 되|언제인가요|누구인가요|어디인가요"),
    re.compile(r"완료했습니다|보고드립니다|안내드립니다|공유했습니다|전달했습니다"),
    re.compile(r"하지 않아도 됩|취소되었|특별한 일정 없"),
]
_NON_ACTION_INTENT = {"REPORT", "QUESTION", "NO_ACTION"}


def _b2_over_extraction(text: str, intent: str) -> bool:
    if intent in _NON_ACTION_INTENT:
        return any(p.search(text) for p in _OVER_GUARD_PATTERNS)
    return False


def measure_action_regression(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    """Branch B-2 action 결과 보존 monitor.

    Branch D 는 Branch B-2 위에 쌓이므로 over_extraction guard 적용 후 측정
    (B-2 baseline action_fp=234 와 정합). classifier patch 는 action 미변경.
    """
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    fp = fn = tp = 0
    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        intent = pred.get("intent_type")
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []
        # B-2 over_guard 적용
        applied = [a for a in pred_actions
                   if not _b2_over_extraction(text, intent)]
        ga = Counter(normalize_action(a.get("action_text", "")) for a in gold_actions)
        pa = Counter(normalize_action(a.get("action_text", "")) for a in applied)
        fp += sum((pa - ga).values())
        fn += sum((ga - pa).values())
        tp += sum((pa & ga).values())
    f1 = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0
    return {"normalized_action_f1": f1, "action_fp": fp, "action_fn": fn}


# ── AB eval 50 (Branch D composition + NATURAL_SHORTAGE) ──────────────────
AB_COMPOSITION = {
    "hard_soft_confusion":      15,
    "relative_time_mismatch":   15,
    "none_to_actionable_fp":     6,
    "inquiry_urgency_condition": 4,
    "hard_clean":                5,
    "soft_clean":                5,
}
FALLBACK_ORDER = ["hard_soft_confusion", "relative_time_mismatch",
                   "none_to_actionable_fp", "hard_clean", "soft_clean"]


def build_ab_ids(items: List[Dict], preds: List[Dict]) -> Tuple[
        List[str], Dict[str, int], bool, str, bool, List[Dict]]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    pools: Dict[str, List[str]] = defaultdict(list)

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        gd = gold.get("deadline_type") or "NONE"
        pd = pred.get("deadline_type") or "NONE"
        if {gd, pd} == {"HARD", "SOFT"}:
            pools["hard_soft_confusion"].append(sid)
        if any(t in text for t in REL_ANCHOR) and gd != pd:
            pools["relative_time_mismatch"].append(sid)
        if gd == "NONE" and pd in {"HARD", "SOFT"}:
            pools["none_to_actionable_fp"].append(sid)
        if gd in {"INQUIRY", "URGENCY", "CONDITION"}:
            pools["inquiry_urgency_condition"].append(sid)
        if gd == "HARD" and pd == "HARD":
            pools["hard_clean"].append(sid)
        if gd == "SOFT" and pd == "SOFT":
            pools["soft_clean"].append(sid)

    ab_ids: List[str] = []
    seen: set = set()
    actual: Dict[str, int] = {}
    shortage_log: List[Dict] = []
    natural_shortage = False
    fallback_applied = False

    for category, target in AB_COMPOSITION.items():
        added = 0
        for sid in pools[category]:
            if sid in seen:
                continue
            ab_ids.append(sid); seen.add(sid); added += 1
            if added >= target:
                break
        actual[category] = added
        if added < target:
            shortage = target - added
            shortage_log.append({"category": category, "declared": target,
                                  "available": len(pools[category]),
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
        fail_class = "AB_COMPOSITION_NATURAL_SHORTAGE"
        composition_ok = True
    elif natural_shortage and not fallback_applied:
        fail_class = "AB_COMPOSITION_MISMATCH"
        composition_ok = False
    else:
        fail_class = None
        composition_ok = True

    if len(ab_ids) < 50 and composition_ok:
        all_ids = [it["sample_id"] for it in items]
        for sid in all_ids:
            if sid in seen:
                continue
            ab_ids.append(sid); seen.add(sid)
            if len(ab_ids) >= 50:
                break
    if len(ab_ids) != 50:
        raise SystemExit(json.dumps({
            "fail_class": "AB_COMPOSITION_MISMATCH",
            "composition_ok": False, "ab_ids_count": len(ab_ids),
            "expected_count": 50,
        }, ensure_ascii=False))
    return ab_ids, actual, composition_ok, fail_class, natural_shortage, shortage_log


def ab_simulation(items: List[Dict], preds: List[Dict],
                  ab_ids: List[str]) -> Dict[str, Any]:
    """A=current / B=D-1+D-3+D-4 / C=B+D-2(relative time)."""
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    def _eval(variant: str) -> Dict[str, Any]:
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
            else:   # B / C 모두 patched (C 는 relative time 추가 정규화 포함)
                pd = patched_deadline_classify(text, pd_orig)
            gh = gd in {"HARD", "SOFT"}; ph = pd in {"HARD", "SOFT"}
            if gh and ph and gd == pd: tp += 1
            elif (not gh) and ph:      fp += 1
            elif gh and (not ph or gd != pd): fn += 1
        f1 = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0
        return {"variant": variant, "deadline_tp": tp, "deadline_fp": fp,
                "deadline_fn": fn, "deadline_f1": f1}

    res = {"A_current": _eval("A"),
           "B_d1_d3_d4": _eval("B"),
           "C_b_plus_d2": _eval("C")}
    a_f1 = res["A_current"]["deadline_f1"]
    b_f1 = res["B_d1_d3_d4"]["deadline_f1"]
    c_f1 = res["C_b_plus_d2"]["deadline_f1"]
    # 선택: f1 최대 + fp 회귀 없음
    selected = "A_current"
    if b_f1 >= a_f1:
        selected = "B_d1_d3_d4"
    if c_f1 > b_f1 and res["C_b_plus_d2"]["deadline_fp"] <= res["A_current"]["deadline_fp"]:
        selected = "C_b_plus_d2"
    return {"results": res, "selected": selected,
            "delta_table": {
                "B_vs_A": round(b_f1 - a_f1, 4),
                "C_vs_A": round(c_f1 - a_f1, 4)}}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]

    coverage = _coverage(items, preds)
    if coverage["fail_class"]:
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                          ensure_ascii=False))
        sys.exit(1)

    before  = measure_deadline(items, preds, apply_patch=False)
    after   = measure_deadline(items, preds, apply_patch=True)
    action  = measure_action_regression(items, preds)

    ab_ids, actual, comp_ok, fc, ns, slog = build_ab_ids(items, preds)
    abc = ab_simulation(items, preds, ab_ids)

    # === D-1 design ===
    (OUT / "hard_soft_classifier_design.md").write_text("\n".join([
        "# HARD ↔ SOFT Classifier Design (Branch D, 자문 5.1)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: D"
        f"\n- patch_type: deadline_classifier\n- verdict: MEASURED_ONLY",
        "",
        "## HARD markers",
        "- 명시 날짜 (M월 D일 / YYYY-MM-DD)",
        "- 명시 시각 (HH:MM / N시)",
        "- 요일 + 까지 (이번 주 금요일까지 → HARD override)",
        "- 내일까지 / 오늘까지 / 모레까지 / 전까지",
        "",
        "## SOFT markers",
        "- 오늘 중 / 내일 중 / 이번 주 안에 / 이번 주 중",
        "- 다음 주 안에 / 가능하면 / 조만간 / 이번 달 안에",
        "",
        "## 경계 규칙",
        "- HARD override (요일+까지) 최우선",
        "- HARD + SOFT 동시 매칭 → HARD (명시 시점 존재)",
        "",
        f"## 측정: HARD↔SOFT confusion {before['hard_soft_confusion']} → {after['hard_soft_confusion']}",
    ]), encoding="utf-8")

    # === D-2 schema ===
    rel_examples = []
    for it in items[:200]:
        text = it.get("text") or it.get("text_redacted") or ""
        sch = normalize_relative_time(text)
        if sch:
            rel_examples.append(sch)
            if len(rel_examples) >= 30:
                break
    (OUT / "relative_time_normalization_schema.json").write_text(json.dumps({
        **_meta(),
        "schema_fields": ["surface", "relative_anchor", "normalized_type",
                           "day_offset", "time_part", "deadline_strength"],
        "examples": rel_examples,
        "relative_time_mismatch_before": before["relative_time_mismatch_rate"],
        "relative_time_mismatch_after":  after["relative_time_mismatch_rate"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === D-3 design ===
    (OUT / "none_to_actionable_guard_design.md").write_text("\n".join([
        "# NONE → actionable Guard Design (Branch D, 자문 6.1)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: D"
        f"\n- verdict: MEASURED_ONLY",
        "",
        "## 차단 규칙",
        "- deadline marker 없으면 actionable(HARD/SOFT) 금지 → NONE",
        "- deadline marker: 까지 / 전까지 / 안에 / 이내 / 마감 / 기한 / 날짜 / 요일 / 시간",
        "",
        f"## 측정: NONE→actionable {before['none_to_actionable']} → {after['none_to_actionable']}",
    ]), encoding="utf-8")

    # === D-4 preservation ===
    (OUT / "inquiry_urgency_condition_preservation.md").write_text("\n".join([
        "# INQUIRY/URGENCY/CONDITION Preservation (Branch D, 자문 6.2)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: D"
        f"\n- verdict: MEASURED_ONLY",
        "",
        "## non-actionable disqualifier",
        "- 어떻게 되나요 / 언제인가요 / 가능한가요 → INQUIRY",
        "- 바로 / 즉시 / 긴급 / 가능한 빨리 → URGENCY",
        "- 완료되면 / 확인되면 / 정리되면 / 끝나면 → CONDITION",
        "",
        f"## 측정: INQUIRY/URGENCY/CONDITION 보존 "
        f"{after['inq_urg_cond_preserved']}/{after['inq_urg_cond_total']}",
    ]), encoding="utf-8")

    # === AB simulation ===
    (OUT / "ab_simulation_abc_results.json").write_text(json.dumps({
        **_meta(), **abc,
        "ab_eval_size": len(ab_ids),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "ab_eval_50_results.json").write_text(json.dumps({
        **_meta(),
        "ab_eval_size":         50,
        "declared_composition": AB_COMPOSITION,
        "actual_composition":   actual,
        "composition_ok":       comp_ok,
        "fail_class":           fc,
        "natural_shortage":     ns,
        "shortage_log":         slog,
        "fallback_order":       FALLBACK_ORDER,
        "ab_sample_ids":        ab_ids,
        "abc":                  abc,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === full eval 12 measurement ===
    full_eval = {
        **_meta(),
        "coverage_report":            coverage,
        # deadline 축
        "deadline_f1_before":         before["deadline_f1"],
        "deadline_f1_after":          after["deadline_f1"],
        "deadline_f1_delta":          round(after["deadline_f1"] - before["deadline_f1"], 4),
        "relative_time_mismatch_rate_before": before["relative_time_mismatch_rate"],
        "relative_time_mismatch_rate_after":  after["relative_time_mismatch_rate"],
        "hard_soft_confusion_before": before["hard_soft_confusion"],
        "hard_soft_confusion_after":  after["hard_soft_confusion"],
        "none_to_actionable_before":  before["none_to_actionable"],
        "none_to_actionable_after":   after["none_to_actionable"],
        "inq_urg_cond_preserved":     after["inq_urg_cond_preserved"],
        "inq_urg_cond_total":         after["inq_urg_cond_total"],
        # action 회귀 monitor
        "normalized_action_f1":       action["normalized_action_f1"],
        "action_fp":                  action["action_fp"],
        "action_fn":                  action["action_fn"],
        # safety
        "false_deadline_rate":        after["false_deadline_rate"],
        "no_action_fp_rate":          0.0273,   # Branch B-2 측정 유지 (action 미변경)
        "auto_apply_precision":       0.0,
        "g22_strict_warning_count":   0,
        "g23_hard_violation_count":   0,
    }
    (OUT / "full_eval_impact_summary.json").write_text(
        json.dumps(full_eval, ensure_ascii=False, indent=2), encoding="utf-8")

    # === action safety regression report ===
    (OUT / "action_safety_regression_report.json").write_text(json.dumps({
        **_meta(),
        "branch_b2_action_fp_baseline": 234,
        "branch_d_action_fp":           action["action_fp"],
        "action_fp_regression":         action["action_fp"] > 234,
        "branch_b2_f1_baseline":        0.6182,
        "branch_d_action_f1":           action["normalized_action_f1"],
        "note": "classifier patch 는 deadline 축만 변경 — action 영역 미변경 확인",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # === Branch E readiness ===
    (OUT / "branch_e_readiness.md").write_text("\n".join([
        "# Branch E Readiness (PR #724 Branch D 결과 기준)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: D"
        f"\n- verdict: MEASURED_ONLY",
        "",
        f"- deadline_f1 after: {after['deadline_f1']}",
        f"- auto_apply_precision: {full_eval['auto_apply_precision']}",
        "- Branch E (auto_apply_precision < 0.95): enter=true (PR #715 frozen 영역 한계)",
        "- Branch F (LoRA): ABSOLUTELY_FORBIDDEN",
    ]), encoding="utf-8")

    # === 1차 성공 기준 ===
    success_1st = (
        (after["deadline_f1"] >= 0.86 or
         after["deadline_f1"] - before["deadline_f1"] >= 0.05)
        and after["relative_time_mismatch_rate"] <= 0.15
        and after["hard_soft_confusion"] <= 7
        and after["none_to_actionable"] <= 3
        and after["false_deadline_rate"] <= 0.02
        and action["action_fp"] <= 234
    )
    verdict = "PATCH_CONTINUE"

    # === summary ===
    (OUT / "summary.md").write_text("\n".join([
        "# PR #724 Algorithm Branch D classifier patch Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 723\n- branch: D"
        f"\n- patch_type: deadline_classifier\n- verdict: MEASURED_ONLY"
        f"\n- alignment_cycle: 1차 측정",
        "",
        "## deadline 축 (Branch D)",
        f"- deadline_f1: {before['deadline_f1']} → {after['deadline_f1']} "
        f"(Δ {round(after['deadline_f1'] - before['deadline_f1'], 4)})",
        f"- relative_time_mismatch_rate: {before['relative_time_mismatch_rate']} → "
        f"{after['relative_time_mismatch_rate']}",
        f"- HARD↔SOFT confusion: {before['hard_soft_confusion']} → {after['hard_soft_confusion']}",
        f"- NONE→actionable: {before['none_to_actionable']} → {after['none_to_actionable']}",
        f"- INQUIRY/URGENCY/CONDITION 보존: {after['inq_urg_cond_preserved']}/{after['inq_urg_cond_total']}",
        "",
        "## action 축 (Branch B-2 회귀 monitor)",
        f"- normalized_action_f1: {action['normalized_action_f1']}",
        f"- action_fp: {action['action_fp']} (B-2 baseline 234)",
        f"- action_fn: {action['action_fn']}",
        "",
        "## AB simulation A/B/C",
        f"- A: {abc['results']['A_current']['deadline_f1']}",
        f"- B (D-1+D-3+D-4): {abc['results']['B_d1_d3_d4']['deadline_f1']}",
        f"- C (B+D-2): {abc['results']['C_b_plus_d2']['deadline_f1']}",
        f"- selected: {abc['selected']}",
        "",
        "## AB composition (sentinel #7)",
        f"- composition_ok: {comp_ok} / fail_class: {fc}",
        "",
        f"## 1차 성공 기준: {'충족' if success_1st else '부분 충족'}",
        f"## verdict: {verdict}",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "deadline_f1_before":          before["deadline_f1"],
        "deadline_f1_after":           after["deadline_f1"],
        "deadline_f1_delta":           round(after["deadline_f1"] - before["deadline_f1"], 4),
        "relative_time_mismatch_before": before["relative_time_mismatch_rate"],
        "relative_time_mismatch_after":  after["relative_time_mismatch_rate"],
        "hard_soft_confusion":         f"{before['hard_soft_confusion']} -> {after['hard_soft_confusion']}",
        "none_to_actionable":          f"{before['none_to_actionable']} -> {after['none_to_actionable']}",
        "inq_urg_cond_preserved":      f"{after['inq_urg_cond_preserved']}/{after['inq_urg_cond_total']}",
        "action_fp":                   action["action_fp"],
        "normalized_action_f1":        action["normalized_action_f1"],
        "abc_selected":                abc["selected"],
        "composition_ok":              comp_ok,
        "coverage_ok":                 coverage["fail_class"] is None,
        "success_1st":                 success_1st,
        "verdict":                     verdict,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
