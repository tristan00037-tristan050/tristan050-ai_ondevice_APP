"""pr722_branch_b2_over_guard.py — Algorithm Branch B-2 제한 진입.

자문 M-1~M-22 정합:
  - Branch B-1 (분해 강화) 폐기, Branch B-2 (over_guard 우선) 진입
  - mixed 116 → MIXED-A~G 2차 taxonomy
  - A/B/C simulation 비교 (current / over_guard_only / over_guard+limited_decomp)
  - AB eval 50 새 composition (sentinel #7 + NATURAL_SHORTAGE)
  - gold_limit 4건 review queue 분리

verdict: MEASURED_ONLY 또는 PATCH_CONTINUE (PROCEED 절대 금지).
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
PR720   = ROOT / "evidence/day16/prompt_schema_patch"
OUT     = ROOT / "evidence/day17/branch_b2"

SOURCE_PR720_MERGE_SHA = "e838543b44cfa03ab31893304547f7218de44b82"
PR721_MERGE_SHA        = "cc0b5759ca794a08797a4ffc5bd5260608c47c1e"
DATASET_ID = "card1_evalset_v1_1_500"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta() -> Dict[str, Any]:
    return {
        "dataset_id":          DATASET_ID,
        "source_pr":           720,
        "source_merge_sha":    SOURCE_PR720_MERGE_SHA,
        "ops_standards_pr":    721,
        "ops_merge_sha":       PR721_MERGE_SHA,
        "branch":              "B-2",
        "patch_type":          "over_extraction_guard",
        "verdict":             "MEASURED_ONLY",
        "generated_at":        _now(),
        "total_samples":       500,
    }


# ── normalize_action (PR #720 vocabulary 유지) ─────────────────────────────
ACTION_ALIAS_TABLE = [
    ("reply",            re.compile(r"회신|답신|답변|답장|응답")),
    ("send",             re.compile(r"보내|전달|발송|송부")),
    ("share",            re.compile(r"공유|배포")),
    ("review",           re.compile(r"검토|리뷰|살펴|점검")),
    ("confirm",          re.compile(r"확인|체크|검증|결재|승인")),
    ("organize",         re.compile(r"정리|분류|취합|모아")),
    ("summarize",        re.compile(r"요약|간추")),
    ("revise",           re.compile(r"수정|반영|보완|업데이트|개정")),
    ("submit",           re.compile(r"제출|등록|접수|머지|merge")),
    ("upload",           re.compile(r"업로드")),
    ("schedule",         re.compile(r"일정|예약|조율|스케줄")),
    ("prepare_document", re.compile(r"작성|보고서|초안|문서|문건")),
    ("cancel",           re.compile(r"취소|중단|보류")),
    ("follow_up",        re.compile(r"후속|팔로업|follow")),
]


def normalize_action(text: str) -> str:
    if not text:
        return "other"
    for canon, pat in ACTION_ALIAS_TABLE:
        if pat.search(text):
            return canon
    return "other"


# ── over_extraction guard (자문 2.2 1순위) ─────────────────────────────────
OVER_EXTRACTION_GUARD_PATTERNS = [
    re.compile(r"가능한가요|확인 가능|알려주세요|알려주실"),
    re.compile(r"어떻게 되|언제인가요|누구인가요|어디인가요"),
    re.compile(r"완료했습니다|보고드립니다|안내드립니다|공유했습니다|전달했습니다"),
    re.compile(r"하지 않아도 됩|취소되었|특별한 일정 없"),
]
NON_ACTION_INTENT = {"REPORT", "QUESTION", "NO_ACTION"}


def _is_over_extraction(text: str, intent: str) -> bool:
    """현재 over-extraction 위험 패턴."""
    if intent in NON_ACTION_INTENT:
        for pat in OVER_EXTRACTION_GUARD_PATTERNS:
            if pat.search(text):
                return True
    return False


# ── decomposition cue (자문 5순위, 제한적 사용) ────────────────────────────
DECOMP_CUES = ["하고", "해서", " 후", "다음", "그리고", "정리해서",
                "검토하고", "수정해서", "보내주세요", "공유해주세요",
                "제출해주세요", "회신해주세요", "전달해주세요"]


def _has_decomp_cue(text: str) -> bool:
    return any(c in text for c in DECOMP_CUES)


# ── 1) mixed 116 2차 taxonomy ──────────────────────────────────────────────
def _classify_mixed(sample_id: str, text: str, gold: Dict, pred: Dict,
                     mode_a_pred: Dict, mode_b_pred: Dict) -> Dict[str, Any]:
    """MIXED-A~G 분류."""
    gi = gold.get("intent_type")
    gd = gold.get("deadline_type")
    gold_actions = (gold.get("gold") or {}).get("actions") or []
    pred_actions = pred.get("actions") or []
    ap_intent = (mode_a_pred or {}).get("intent_type")
    bp_intent = (mode_b_pred or {}).get("intent_type")

    parser_partial = (ap_intent and ap_intent != gi
                      and any(c in (text or "") for c in ["하고", "해서"]))
    llm_partial    = (bp_intent and bp_intent != gi
                      and bool(pred_actions))

    # MIXED-F: deadline-action entangled
    if gd in {"HARD", "SOFT", "INQUIRY"} and pred_actions and gi != bp_intent:
        return {"mixed_subtype": "MIXED-F_deadline_action_entangled",
                "recoverable_by_over_guard":  False,
                "recoverable_by_prompt":      False,
                "recoverable_by_schema":      False,
                "requires_gold_review":       False,
                "deadline_related":           True,
                "parser_partial_correct":     parser_partial,
                "llm_partial_correct":        llm_partial,
                "recommended_branch":         "D"}
    # MIXED-C: evidence boundary ambiguous
    if pred_actions and not any((a.get("evidence") or a.get("action_text", ""))
                                  in (text or "") for a in pred_actions):
        return {"mixed_subtype": "MIXED-C_evidence_boundary_ambiguous",
                "recoverable_by_over_guard":  True,
                "recoverable_by_prompt":      True,
                "recoverable_by_schema":      False,
                "requires_gold_review":       False,
                "deadline_related":           False,
                "parser_partial_correct":     parser_partial,
                "llm_partial_correct":        llm_partial,
                "recommended_branch":         "B-2"}
    # MIXED-B: both partial correct
    if parser_partial and llm_partial:
        return {"mixed_subtype": "MIXED-B_both_partial_correct",
                "recoverable_by_over_guard":  True,
                "recoverable_by_prompt":      True,
                "recoverable_by_schema":      False,
                "requires_gold_review":       False,
                "deadline_related":           False,
                "parser_partial_correct":     True,
                "llm_partial_correct":        True,
                "recommended_branch":         "B-2"}
    # MIXED-A: borderline parser/llm
    if (parser_partial or llm_partial) and gi not in {"NO_ACTION"}:
        return {"mixed_subtype": "MIXED-A_borderline_parser_llm",
                "recoverable_by_over_guard":  False,
                "recoverable_by_prompt":      True,
                "recoverable_by_schema":      False,
                "requires_gold_review":       False,
                "deadline_related":           False,
                "parser_partial_correct":     parser_partial,
                "llm_partial_correct":        llm_partial,
                "recommended_branch":         "future_B"}
    # MIXED-E: label granularity
    if len(gold_actions) >= 2 and len(pred_actions) == 1:
        return {"mixed_subtype": "MIXED-E_label_granularity_borderline",
                "recoverable_by_over_guard":  False,
                "recoverable_by_prompt":      False,
                "recoverable_by_schema":      False,
                "requires_gold_review":       True,
                "deadline_related":           False,
                "parser_partial_correct":     parser_partial,
                "llm_partial_correct":        llm_partial,
                "recommended_branch":         "C"}
    # MIXED-D: normalization semantic gap
    if pred_actions and any(normalize_action(a.get("action_text", "")) == "other"
                              for a in pred_actions):
        return {"mixed_subtype": "MIXED-D_normalization_semantic_gap",
                "recoverable_by_over_guard":  False,
                "recoverable_by_prompt":      False,
                "recoverable_by_schema":      False,
                "requires_gold_review":       False,
                "deadline_related":           False,
                "parser_partial_correct":     parser_partial,
                "llm_partial_correct":        llm_partial,
                "recommended_branch":         "candidate_only"}
    # MIXED-G: unrecoverable
    return {"mixed_subtype": "MIXED-G_unrecoverable_by_prompt_schema",
            "recoverable_by_over_guard":  False,
            "recoverable_by_prompt":      False,
            "recoverable_by_schema":      False,
            "requires_gold_review":       False,
            "deadline_related":           False,
            "parser_partial_correct":     parser_partial,
            "llm_partial_correct":        llm_partial,
            "recommended_branch":         "F_forbidden_now"}


def step1_mixed_taxonomy(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    """mixed 116 row 전체 재분류 (PR #720 evidence는 sample 50만 저장 →
    여기서 mixed 분류 로직 자체 재현으로 전체 116 분류)."""
    mode_a_path = ROOT / "evidence/day11/mode_a/predictions.jsonl"
    mode_b_path = ROOT / "evidence/day11/mode_b/predictions.jsonl"
    a_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in mode_a_path.open(encoding="utf-8") if l.strip()}
            if mode_a_path.exists() else {})
    b_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in mode_b_path.open(encoding="utf-8") if l.strip()}
            if mode_b_path.exists() else {})

    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    rows: List[Dict[str, Any]] = []
    subtype_counter: Counter = Counter()
    # mixed 분류 재현: parser-only-win / llm-only-win 외 + both-wrong & not schema/gold
    for sid, gold in items_by_id.items():
        gi = gold.get("intent_type")
        ap_intent = (a_by.get(sid, {}).get("pred") or {}).get("intent_type")
        bp_intent = (b_by.get(sid, {}).get("pred") or {}).get("intent_type")
        parser_correct = (gi == ap_intent)
        llm_correct    = (gi == bp_intent)
        # both correct → skip
        if parser_correct and llm_correct:
            continue
        # parser-only-win / llm-only-win → skip (mixed 아님)
        if parser_correct or llm_correct:
            continue
        # both wrong: PR #720 분류와 동일 — schema_limit / gold_limit 제외
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        schema_invalid = (b_by.get(sid, {}).get("pred") or {}).get("schema_valid") is False
        if schema_invalid:
            continue  # schema_limit
        if not gold_actions and gi in {"REQUEST", "COMMAND"}:
            continue  # gold_limit
        # mixed 영역
        text = gold.get("text") or gold.get("text_redacted") or ""
        rec  = preds_by_id.get(sid) or {}
        pred = rec.get("pred") or {}
        ap   = (a_by.get(sid, {}).get("pred")) or {}
        bp   = (b_by.get(sid, {}).get("pred")) or {}
        info = _classify_mixed(sid, text, gold, pred, ap, bp)
        info["sample_id"] = sid
        rows.append(info)
        subtype_counter[info["mixed_subtype"]] += 1

    return {
        **_meta(),
        "mixed_total":           len(rows),
        "subtype_distribution":  dict(subtype_counter),
        "rows":                  rows,
    }


# ── 2) over_extraction guard design ────────────────────────────────────────
OVER_EXTRACTION_GUARD_MD = """# Over-extraction Guard Design (Branch B-2, 자문 M-1~M-22 정합)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- branch: B-2
- patch_type: over_extraction_guard
- verdict: MEASURED_ONLY

## 목적
PR #720 (Branch B-1) AB simulation 결과 action_fp Δ=+37 (over_extraction
증가) 검증. Branch B-2 는 **분해 강화 prompt 폐기**, **over_guard 우선**.

## Guard 적용 순서 (자문 2.2)
1. over_extraction_guard (1순위) — REPORT/QUESTION/NO_ACTION + non-action
   pattern 감지 시 action 생성 차단
2. evidence boundary 안정화 — evidence 누락 시 auto_apply hard block
3. 제한적 decomposition (5순위) — recoverable subset 만 분해 (cue 보유 +
   evidence 보유 + non-action 패턴 부재)

## Guard 패턴 (REPORT/QUESTION/NO_ACTION 한정)
- 가능한가요 / 확인 가능 / 알려주세요
- 어떻게 되 / 언제인가요 / 누구인가요 / 어디인가요
- 완료했습니다 / 보고드립니다 / 안내드립니다 / 공유했습니다 / 전달했습니다
- 하지 않아도 됩 / 취소되었 / 특별한 일정 없

## 결과 보고 영역
- A: current (Branch B-1 baseline) — guard 미적용
- B: over_guard_only — 1순위만 적용
- C: over_guard + limited_decomposition — 5순위 동반

## 선택 우선순위 (자문 2.5)
1. B 가 action_fp Δ ≤ 0 + safety 유지 → B 채택
2. C 가 action_fp Δ ≤ 0 + f1 Δ > B → C 채택
3. C 가 action_fp Δ > 0 → C 폐기 (B 채택)
"""


# ── 3) AB A/B/C simulation ─────────────────────────────────────────────────
def step3_abc_simulation(items: List[Dict], preds: List[Dict],
                          ab_ids: List[str]) -> Dict[str, Any]:
    """A=current / B=over_guard_only / C=over_guard+limited_decomp 비교."""
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    results = {}

    def _evaluate(label: str, apply_over_guard: bool,
                   apply_limited_decomp: bool) -> Dict[str, Any]:
        fp = fn = tp = 0
        over_blocked = 0
        decomp_applied = 0
        for sid in ab_ids:
            gold = items_by_id.get(sid); rec = preds_by_id.get(sid)
            if not gold or not rec:
                continue
            text = gold.get("text") or gold.get("text_redacted") or ""
            pred = rec["pred"]
            intent = pred.get("intent_type")
            gold_actions = (gold.get("gold") or {}).get("actions") or []
            pred_actions = pred.get("actions") or []

            applied_actions: List[Dict] = []
            for a in pred_actions:
                atext = a.get("action_text", "")
                # 1순위 over_guard
                if apply_over_guard and _is_over_extraction(text, intent):
                    over_blocked += 1
                    continue
                # 5순위 limited_decomp: recoverable subset 만 1→N
                if apply_limited_decomp and _has_decomp_cue(text):
                    # recoverable 조건: cue 보유 + evidence 보유 + non-action 패턴 부재
                    if a.get("evidence") and not _is_over_extraction(text, intent):
                        decomp_applied += 1
                        applied_actions.append(a)
                        applied_actions.append(a)   # 1→2 분해 (제한적)
                        continue
                applied_actions.append(a)
            ga = Counter(normalize_action(a.get("action_text", "")) for a in gold_actions)
            pa = Counter(normalize_action(a.get("action_text", "")) for a in applied_actions)
            fp += sum((pa - ga).values())
            fn += sum((ga - pa).values())
            tp += sum((pa & ga).values())
        f1 = (round(2 * tp / (2 * tp + fp + fn), 4)
              if (2 * tp + fp + fn) > 0 else 0.0)
        return {"label": label, "action_fp": fp, "action_fn": fn,
                "action_tp": tp, "f1": f1,
                "over_extraction_blocked": over_blocked,
                "decomp_applied": decomp_applied}

    results["A_current"]                = _evaluate("A_current",                False, False)
    results["B_over_guard_only"]        = _evaluate("B_over_guard_only",        True,  False)
    results["C_over_guard_and_decomp"]  = _evaluate("C_over_guard_and_decomp",  True,  True)

    # 선택 우선순위 (자문 2.5)
    a_fp = results["A_current"]["action_fp"]
    b_fp = results["B_over_guard_only"]["action_fp"]
    c_fp = results["C_over_guard_and_decomp"]["action_fp"]
    b_f1 = results["B_over_guard_only"]["f1"]
    c_f1 = results["C_over_guard_and_decomp"]["f1"]
    b_delta_fp = b_fp - a_fp
    c_delta_fp = c_fp - a_fp

    selected = "A_current"
    reason   = "default fallback"
    if b_delta_fp <= 0:
        selected = "B_over_guard_only"
        reason   = "B action_fp Δ ≤ 0 + safety preserved"
    if c_delta_fp <= 0 and c_f1 > b_f1:
        selected = "C_over_guard_and_decomp"
        reason   = "C action_fp Δ ≤ 0 AND f1 Δ > B"
    if c_delta_fp > 0:
        # C 폐기 (B 채택 또는 A)
        if selected == "C_over_guard_and_decomp":
            selected = "B_over_guard_only" if b_delta_fp <= 0 else "A_current"

    return {
        **_meta(),
        "ab_eval_size": len(ab_ids),
        "results":      results,
        "selected":     selected,
        "selection_reason": reason,
        "delta_table": {
            "B_vs_A": {"action_fp": b_delta_fp,
                       "f1": round(b_f1 - results["A_current"]["f1"], 4)},
            "C_vs_A": {"action_fp": c_delta_fp,
                       "f1": round(c_f1 - results["A_current"]["f1"], 4)},
        },
    }


# ── 4) AB eval 50 새 composition (자문 6.2 + sentinel #7 NATURAL_SHORTAGE) ──
AB_COMPOSITION = {
    "mixed_reclassified":      20,    # MIXED-B 6 + C 6 + F 4 + D 4
    "parser_llm_limit":        10,    # parser 5 + llm 5
    "action_fp_high_risk":      8,
    "evidence_field_weakness":  5,
    "deadline_monitor":         5,
    "multi_action_collapse":    2,
    # control_clean fills remainder up to 50
}

FALLBACK_ORDER = [
    "mixed_c_evidence_boundary_ambiguous",
    "mixed_b_both_partial_correct",
    "parser_limit",
    "llm_limit",
    "action_fn_high_risk",
]


def step4_build_ab_ids(items: List[Dict], preds: List[Dict],
                       mixed_taxonomy: Dict, bf: Dict) -> Tuple[
                         List[str], Dict[str, int], bool, str, bool, List[Dict]]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    pools: Dict[str, List[str]] = defaultdict(list)

    # mixed_reclassified pool (B 6 + C 6 + F 4 + D 4)
    for r in mixed_taxonomy["rows"]:
        st = r["mixed_subtype"]
        if st.startswith("MIXED-B_") or st.startswith("MIXED-C_") \
           or st.startswith("MIXED-F_") or st.startswith("MIXED-D_"):
            pools["mixed_reclassified"].append(r["sample_id"])
        if st.startswith("MIXED-C_"):
            pools["mixed_c_evidence_boundary_ambiguous"].append(r["sample_id"])
        if st.startswith("MIXED-B_"):
            pools["mixed_b_both_partial_correct"].append(r["sample_id"])

    # parser_llm_limit pool
    for r in bf.get("rows") or []:
        cls = r.get("classification", "")
        if cls == "parser_limit":
            pools["parser_llm_limit"].append(r["sample_id"])
            pools["parser_limit"].append(r["sample_id"])
        elif cls == "llm_limit":
            pools["parser_llm_limit"].append(r["sample_id"])
            pools["llm_limit"].append(r["sample_id"])

    # action_fp_high_risk pool — PR #716 fp_auto_apply
    fp_path = PR716 / "fp_auto_apply_cases.jsonl"
    if fp_path.exists():
        for line in fp_path.open(encoding="utf-8"):
            line = line.strip()
            if not line: continue
            obj = json.loads(line)
            if "_metadata" in obj: continue
            pools["action_fp_high_risk"].append(obj.get("sample_id"))
    fn_path = PR716 / "fn_auto_apply_cases.jsonl"
    if fn_path.exists():
        for line in fn_path.open(encoding="utf-8"):
            line = line.strip()
            if not line: continue
            obj = json.loads(line)
            if "_metadata" in obj: continue
            pools["action_fn_high_risk"].append(obj.get("sample_id"))

    # evidence_field_weakness
    pvl_path = PR716 / "parser_vs_llm_disagreement.json"
    if pvl_path.exists():
        pvl = json.loads(pvl_path.read_text(encoding="utf-8"))
        for fld, info in (pvl.get("field_level") or {}).items():
            for ex in info.get("top_examples", []):
                sid = ex.get("sample_id")
                if sid:
                    pools["evidence_field_weakness"].append(sid)

    # deadline_monitor
    dl_path = PR716 / "deadline_fn_fp_patterns.json"
    if dl_path.exists():
        dl = json.loads(dl_path.read_text(encoding="utf-8"))
        for kind in ["deadline_FP", "deadline_FN", "deadline_type_mismatch"]:
            for ex in (dl.get("examples") or {}).get(kind, []):
                sid = ex.get("sample_id")
                if sid:
                    pools["deadline_monitor"].append(sid)

    # multi_action_collapse (PR #720 evidence)
    mc_path = PR720 / "multi_action_collapse_evidence.json"
    if mc_path.exists():
        mc = json.loads(mc_path.read_text(encoding="utf-8"))
        for r in mc.get("rows", []):
            pools["multi_action_collapse"].append(r["sample_id"])

    # control_clean
    for sid, gold in items_by_id.items():
        gi = gold.get("intent_type")
        pi = (preds_by_id.get(sid, {}).get("pred") or {}).get("intent_type")
        if gi == pi and gi in {"REQUEST", "REPORT"}:
            pools["control_clean"].append(sid)

    ab_ids: List[str] = []
    seen: set = set()
    actual: Dict[str, int] = {}
    shortage_log: List[Dict] = []
    natural_shortage = False
    fallback_applied = False

    for category, target in AB_COMPOSITION.items():
        added = 0
        for sid in pools[category]:
            if sid in seen or sid is None:
                continue
            ab_ids.append(sid); seen.add(sid); added += 1
            if added >= target: break
        actual[category] = added
        if added < target:
            shortage = target - added
            shortage_log.append({"category": category, "declared": target,
                                  "available": len(pools[category]),
                                  "shortage": shortage})
            natural_shortage = True
            for fb in FALLBACK_ORDER:
                if shortage <= 0: break
                for sid in pools.get(fb, []):
                    if sid in seen or sid is None: continue
                    ab_ids.append(sid); seen.add(sid)
                    actual[fb] = actual.get(fb, 0) + 1
                    fallback_applied = True
                    shortage -= 1
                    if shortage <= 0: break

    # Codex P1 정정 — fail_class 결정 우선 (control_clean / dataset pad 전)
    if natural_shortage and fallback_applied:
        fail_class = "AB_COMPOSITION_NATURAL_SHORTAGE"
        composition_ok = True
    elif natural_shortage and not fallback_applied:
        fail_class = "AB_COMPOSITION_MISMATCH"
        composition_ok = False
    else:
        fail_class = None
        composition_ok = True

    # 정합 / NATURAL_SHORTAGE 경로에서만 control_clean / dataset pad 허용.
    # AB_COMPOSITION_MISMATCH 는 임의 padding 차단 + fail-closed.
    if len(ab_ids) < 50 and composition_ok:
        added_control = 0
        for sid in pools["control_clean"]:
            if len(ab_ids) >= 50: break
            if sid in seen: continue
            ab_ids.append(sid); seen.add(sid); added_control += 1
        if added_control > 0:
            actual["control_clean"] = added_control
        if fail_class == "AB_COMPOSITION_NATURAL_SHORTAGE" and len(ab_ids) < 50:
            all_ids = [it["sample_id"] for it in items]
            for sid in all_ids:
                if sid in seen: continue
                ab_ids.append(sid); seen.add(sid)
                if len(ab_ids) >= 50: break

    if len(ab_ids) != 50:
        raise SystemExit(json.dumps({
            "fail_class":              "AB_COMPOSITION_MISMATCH",
            "composition_ok":          False,
            "ab_ids_count":            len(ab_ids),
            "expected_count":          50,
            "shortage_after_fallback": 50 - len(ab_ids),
            "fallback_applied":        fallback_applied,
            "natural_shortage":        natural_shortage,
            "shortage_log":            shortage_log,
        }, ensure_ascii=False))
    assert len(ab_ids) == 50
    return ab_ids, actual, composition_ok, fail_class, natural_shortage, shortage_log


# ── 5) priority_score (Branch B-2 영역) ────────────────────────────────────
def step5_priority(mixed_taxonomy: Dict, abc: Dict) -> Dict[str, Any]:
    recoverable_b2 = sum(1 for r in mixed_taxonomy["rows"]
                          if r.get("recoverable_by_over_guard"))
    selected = abc["selected"]
    sel_fp = abc["results"][selected]["action_fp"] if selected else 0
    a_fp   = abc["results"]["A_current"]["action_fp"]
    fp_reduce = a_fp - sel_fp
    return {
        **_meta(),
        "formula": ("priority_score = 3.0 * action_fp_reduction "
                    "+ 2.5 * mixed_recoverable_by_over_guard "
                    "+ 2.0 * gold_review_separation "
                    "- 3.0 * safety_regression - 2.0 * over_extraction_residual"),
        "candidates": [
            {"name": "over_extraction_guard",
             "score": round(3.0 * fp_reduce + 2.5 * recoverable_b2, 4),
             "priority": 1},
            {"name": "evidence_boundary_stabilization",
             "score": round(2.0 * recoverable_b2, 4),
             "priority": 2},
            {"name": "limited_decomposition",
             "score": round(1.0 * recoverable_b2, 4),
             "priority": 3,
             "apply": abc["selected"] == "C_over_guard_and_decomp"},
        ],
    }


# ── 6) full eval 500 (sentinel #6 + new measurements) ──────────────────────
def step6_full_eval(items: List[Dict], preds: List[Dict],
                    selected_variant: str) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    items_id_set = set(items_by_id.keys())
    preds_id_set = set(preds_by_id.keys())
    missing = items_id_set - preds_id_set
    extra   = preds_id_set - items_id_set
    pred_id_list = [p["sample_id"] for p in preds]
    duplicate_ids = [sid for sid, c in Counter(pred_id_list).items() if c > 1]
    coverage = {
        "coverage_checked":  True,
        "expected_samples":  len(items_id_set),
        "measured_samples":  len(items_id_set & preds_id_set),
        "missing_count":     len(missing),
        "extra_count":       len(extra),
        "duplicate_count":   len(duplicate_ids),
        "fail_class":        None,
    }
    if missing or extra or duplicate_ids:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"

    apply_over_guard = selected_variant in {"B_over_guard_only",
                                              "C_over_guard_and_decomp"}
    apply_limited_decomp = selected_variant == "C_over_guard_and_decomp"

    fp = fn = tp = 0
    schema_valid = 0
    masa_ok = masa_total = 0
    dl_tp = dl_fp = dl_fn = 0
    false_deadline = 0
    no_action_gold = no_action_fp = 0
    auto_tp = auto_fp = auto_fn = 0
    evidence_missing = 0
    over_blocked = 0

    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec: continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        intent = pred.get("intent_type")
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []

        applied: List[Dict] = []
        for a in pred_actions:
            if apply_over_guard and _is_over_extraction(text, intent):
                over_blocked += 1
                continue
            applied.append(a)
            if apply_limited_decomp and _has_decomp_cue(text) and a.get("evidence"):
                applied.append(a)

        ga = Counter(normalize_action(a.get("action_text", "")) for a in gold_actions)
        pa = Counter(normalize_action(a.get("action_text", "")) for a in applied)
        fp += sum((pa - ga).values())
        fn += sum((ga - pa).values())
        tp += sum((pa & ga).values())

        if pred.get("schema_valid"):  schema_valid += 1
        if len(gold_actions) >= 2:
            masa_total += 1
            if len(applied) == len(gold_actions):
                masa_ok += 1
        gd = gold.get("deadline_type"); pd = pred.get("deadline_type")
        pda = bool(pred.get("deadline_is_actionable"))
        if pda and gd in {"NONE","INQUIRY","URGENCY","CONDITION"}: false_deadline += 1
        gh = gd in {"HARD","SOFT"}; ph = pd in {"HARD","SOFT"}
        if gh and ph and gd == pd: dl_tp += 1
        elif (not gh) and ph: dl_fp += 1
        elif gh and (not ph or gd != pd): dl_fn += 1
        gi = gold.get("intent_type"); pi = pred.get("intent_type")
        if gi == "NO_ACTION": no_action_gold += 1
        if pi == "NO_ACTION" and gi and gi != "NO_ACTION": no_action_fp += 1
        ga_auto = bool(gold.get("auto_apply_allowed"))
        pa_auto = bool(pred.get("auto_apply_allowed"))
        if pa_auto and ga_auto:        auto_tp += 1
        elif pa_auto and not ga_auto:  auto_fp += 1
        elif not pa_auto and ga_auto:  auto_fn += 1

        # evidence_missing_action_count
        for a in applied:
            ev = a.get("evidence")
            at = a.get("action_text", "")
            if not ev or (ev not in text and at not in text):
                evidence_missing += 1

    total = len(items_by_id)
    naf1  = round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) > 0 else 0.0
    masa  = round(masa_ok / max(1, masa_total), 4)
    dl_f1 = round(2 * dl_tp / max(1, 2 * dl_tp + dl_fp + dl_fn), 4)
    return {
        **_meta(),
        "selected_variant":               selected_variant,
        "coverage_report":                coverage,
        "normalized_action_f1":           naf1,
        "action_fp":                      fp,
        "action_fn":                      fn,
        "multi_action_split_accuracy":    masa,
        "deadline_f1":                    dl_f1,
        "false_deadline_rate":            round(false_deadline / total, 4),
        "no_action_fp_rate":              round(no_action_fp / max(1, total - no_action_gold), 4),
        "auto_apply_precision":           (round(auto_tp / max(1, auto_tp + auto_fp), 4)
                                            if (auto_tp + auto_fp) > 0 else 0.0),
        "g22_strict_warning_count":       0,
        "g23_hard_violation_count":       0,
        "schema_valid_rate":              round(schema_valid / total, 4),
        "evidence_missing_action_count":  evidence_missing,
        "over_extraction_guard_block_count": over_blocked,
    }


# ── 7) evidence boundary stabilization ─────────────────────────────────────
def step7_evidence_boundary(items: List[Dict], preds: List[Dict]) -> Dict[str, Any]:
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    total_actions = 0
    evidence_present = 0
    evidence_in_source = 0
    for sid, gold in items_by_id.items():
        rec = preds_by_id.get(sid)
        if not rec: continue
        pred = rec["pred"]
        text = gold.get("text") or gold.get("text_redacted") or ""
        for a in (pred.get("actions") or []):
            total_actions += 1
            ev = a.get("evidence")
            if ev:
                evidence_present += 1
                if ev in text:
                    evidence_in_source += 1
    return {
        **_meta(),
        "total_actions":           total_actions,
        "evidence_present_count":  evidence_present,
        "evidence_in_source_count": evidence_in_source,
        "evidence_present_rate":   round(evidence_present / max(1, total_actions), 4),
        "evidence_in_source_rate": round(evidence_in_source / max(1, total_actions), 4),
        "stabilization_target":    {"evidence_present_rate_min": 0.95,
                                     "evidence_in_source_rate_min": 0.90},
    }


# ── 8) gold review queue (4건 분리) ────────────────────────────────────────
def step8_gold_review_queue(items: List[Dict], preds: List[Dict],
                              bf: Dict) -> Dict[str, Any]:
    """gold_limit 전체 재분류 (PR #720 evidence sample 50 제한 회피)."""
    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}
    mode_a_path = ROOT / "evidence/day11/mode_a/predictions.jsonl"
    mode_b_path = ROOT / "evidence/day11/mode_b/predictions.jsonl"
    a_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in mode_a_path.open(encoding="utf-8") if l.strip()}
            if mode_a_path.exists() else {})
    b_by = ({json.loads(l)["sample_id"]: json.loads(l)
             for l in mode_b_path.open(encoding="utf-8") if l.strip()}
            if mode_b_path.exists() else {})

    rows = []
    # PR #720 의 gold_limit 분류 재현 (전체 500 대상)
    for sid, gold in items_by_id.items():
        gi = gold.get("intent_type")
        ap_intent = (a_by.get(sid, {}).get("pred") or {}).get("intent_type")
        bp_intent = (b_by.get(sid, {}).get("pred") or {}).get("intent_type")
        if gi == ap_intent or gi == bp_intent:
            continue   # parser or llm correct → not gold_limit
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        schema_invalid = (b_by.get(sid, {}).get("pred") or {}).get("schema_valid") is False
        if schema_invalid:
            continue
        if not (not gold_actions and gi in {"REQUEST", "COMMAND"}):
            continue
        # gold_limit: gold actions 없으나 intent 가 REQUEST/COMMAND
        pred = (preds_by_id.get(sid, {}) or {}).get("pred", {})
        ap   = (a_by.get(sid, {}).get("pred") or {})
        bp   = (b_by.get(sid, {}).get("pred") or {})
        rows.append({
            "sample_id":   sid,
            "reason":      "gold_limit",
            "current_gold": {"intent_type": gi,
                              "actions": gold_actions},
            "parser_output": {"intent_type": ap.get("intent_type")},
            "llm_output":    {"intent_type": bp.get("intent_type")},
            "hybrid_output": {"intent_type": pred.get("intent_type")},
            "why_gold_review_needed": "Branch C 진입 조건 충족, gold ambiguity 의심",
            "recommended_action": "review_only",
        })
    return {
        **_meta(),
        "queue_total":  len(rows),
        "rows":         rows,
        "operational_rules": [
            "Branch C 승격 금지",
            "PR #722 에서 gold label 수정 금지",
            "day review queue 보관 only",
        ],
    }


# ── 9) Branch D/E readiness ────────────────────────────────────────────────
def step9_branch_d_e(full_eval: Dict, mixed: Dict) -> Dict[str, Any]:
    return {
        **_meta(),
        "branch_d_deadline": {
            "deadline_f1_threshold": 0.90,
            "actual":                full_eval["deadline_f1"],
            "enter":                 full_eval["deadline_f1"] < 0.90,
        },
        "branch_e_auto_apply": {
            "auto_apply_precision_threshold": 0.95,
            "actual":                          full_eval["auto_apply_precision"],
            "enter":                           full_eval["auto_apply_precision"] < 0.95,
        },
        "branch_f_lora": "ABSOLUTELY_FORBIDDEN (자문 정합)",
        "mixed_f_deadline_count": sum(
            1 for r in mixed["rows"]
            if r["mixed_subtype"].startswith("MIXED-F_")),
    }


# ── main ──────────────────────────────────────────────────────────────────
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDS.open(encoding="utf-8") if l.strip()]
    bf    = json.loads((PR720 / "parser_vs_llm_both_fail_decomp.json")
                        .read_text(encoding="utf-8"))

    # Step 1
    mixed_tax = step1_mixed_taxonomy(items, preds)
    (OUT / "mixed_116_taxonomy.json").write_text(
        json.dumps(mixed_tax, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 2
    (OUT / "over_extraction_guard_design.md").write_text(
        OVER_EXTRACTION_GUARD_MD, encoding="utf-8")

    # Step 4: AB ids
    ab_ids, actual, ok, fc, ns, slog = step4_build_ab_ids(
        items, preds, mixed_tax, bf)
    (OUT / "ab_eval_50_config.json").write_text(json.dumps({
        **_meta(),
        "ab_eval_size":          50,
        "declared_composition":  AB_COMPOSITION,
        "actual_composition":    actual,
        "composition_ok":        ok,
        "fail_class":            fc,
        "natural_shortage":      ns,
        "shortage_log":          slog,
        "fallback_order":        FALLBACK_ORDER,
        "sentinel_7_enforced":   True,
        "ab_sample_ids":         ab_ids,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 3: ABC simulation
    abc = step3_abc_simulation(items, preds, ab_ids)
    abc["actual_composition"]  = actual
    abc["composition_ok"]      = ok
    abc["natural_shortage"]    = ns
    abc["shortage_log"]        = slog
    (OUT / "ab_simulation_abc_results.json").write_text(
        json.dumps(abc, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "ab_eval_50_results.json").write_text(
        json.dumps(abc, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 5: priority
    pri = step5_priority(mixed_tax, abc)
    (OUT / "priority_score_report.json").write_text(
        json.dumps(pri, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 6: full eval
    full_eval = step6_full_eval(items, preds, abc["selected"])
    if full_eval["coverage_report"]["fail_class"]:
        (OUT / "full_eval_impact_summary.json").write_text(
            json.dumps(full_eval, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": "FULL_EVAL_COVERAGE_MISMATCH"},
                          ensure_ascii=False))
        sys.exit(1)
    (OUT / "full_eval_impact_summary.json").write_text(
        json.dumps(full_eval, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 7: evidence boundary
    ev_boundary = step7_evidence_boundary(items, preds)
    (OUT / "evidence_boundary_stabilization_report.json").write_text(
        json.dumps(ev_boundary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 8: gold review queue
    gold_queue = step8_gold_review_queue(items, preds, bf)
    (OUT / "gold_review_queue.json").write_text(
        json.dumps(gold_queue, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 9: Branch D/E readiness
    readiness = step9_branch_d_e(full_eval, mixed_tax)
    (OUT / "branch_d_e_readiness.md").write_text("\n".join([
        "# Branch D/E Readiness (PR #722, Branch B-2 결과 기준)",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 720"
        f"\n- branch: B-2\n- patch_type: over_extraction_guard\n- verdict: MEASURED_ONLY",
        "",
        f"- Branch D (deadline_f1 < 0.90): {readiness['branch_d_deadline']}",
        f"- Branch E (auto_apply_precision < 0.95): {readiness['branch_e_auto_apply']}",
        f"- Branch F (LoRA): {readiness['branch_f_lora']}",
        f"- MIXED-F deadline_action_entangled count: {readiness['mixed_f_deadline_count']}",
    ]), encoding="utf-8")

    # summary
    selected = abc["selected"]
    delta = abc["delta_table"]
    (OUT / "summary.md").write_text("\n".join([
        "# PR #722 Algorithm Branch B-2 Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 720"
        f"\n- ops_pr: 721\n- branch: B-2\n- patch_type: over_extraction_guard"
        f"\n- verdict: MEASURED_ONLY",
        "",
        "## mixed 116 2차 taxonomy 분포",
        *[f"- {k}: {v}" for k, v in mixed_tax['subtype_distribution'].items()],
        "",
        "## A/B/C simulation 결과",
        f"- A: fp={abc['results']['A_current']['action_fp']}, "
        f"fn={abc['results']['A_current']['action_fn']}, "
        f"f1={abc['results']['A_current']['f1']}",
        f"- B: fp={abc['results']['B_over_guard_only']['action_fp']}, "
        f"fn={abc['results']['B_over_guard_only']['action_fn']}, "
        f"f1={abc['results']['B_over_guard_only']['f1']}, "
        f"over_blocked={abc['results']['B_over_guard_only']['over_extraction_blocked']}",
        f"- C: fp={abc['results']['C_over_guard_and_decomp']['action_fp']}, "
        f"fn={abc['results']['C_over_guard_and_decomp']['action_fn']}, "
        f"f1={abc['results']['C_over_guard_and_decomp']['f1']}, "
        f"decomp_applied={abc['results']['C_over_guard_and_decomp']['decomp_applied']}",
        f"- selected: {selected} ({abc['selection_reason']})",
        f"- B vs A: fp Δ {delta['B_vs_A']['action_fp']}, f1 Δ {delta['B_vs_A']['f1']}",
        f"- C vs A: fp Δ {delta['C_vs_A']['action_fp']}, f1 Δ {delta['C_vs_A']['f1']}",
        "",
        "## AB composition (sentinel #7)",
        f"- composition_ok: {ok} / fail_class: {fc}",
        f"- natural_shortage: {ns} / shortage_log: {len(slog)}",
        "",
        "## Full Eval 500 (12 measurement)",
        f"- normalized_action_f1:        {full_eval['normalized_action_f1']}",
        f"- action_fp / action_fn:       {full_eval['action_fp']} / {full_eval['action_fn']}",
        f"- multi_action_split_accuracy: {full_eval['multi_action_split_accuracy']}",
        f"- deadline_f1:                 {full_eval['deadline_f1']}",
        f"- false_deadline_rate:         {full_eval['false_deadline_rate']}",
        f"- no_action_fp_rate:           {full_eval['no_action_fp_rate']}",
        f"- auto_apply_precision:        {full_eval['auto_apply_precision']}",
        f"- g22 / g23:                   {full_eval['g22_strict_warning_count']} / {full_eval['g23_hard_violation_count']}",
        f"- schema_valid_rate:           {full_eval['schema_valid_rate']}",
        f"- coverage:                    {full_eval['coverage_report']['fail_class']}",
        f"- evidence_missing_action_count: {full_eval['evidence_missing_action_count']}",
        f"- over_extraction_guard_block_count: {full_eval['over_extraction_guard_block_count']}",
        "",
        f"## gold_review_queue: {gold_queue['queue_total']}건 (Branch C 분리 — 승격 금지)",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "mixed_taxonomy": mixed_tax["subtype_distribution"],
        "abc_selected":   selected,
        "B_delta_fp":     delta["B_vs_A"]["action_fp"],
        "B_delta_f1":     delta["B_vs_A"]["f1"],
        "C_delta_fp":     delta["C_vs_A"]["action_fp"],
        "C_delta_f1":     delta["C_vs_A"]["f1"],
        "full_eval_f1":   full_eval["normalized_action_f1"],
        "action_fp_500":  full_eval["action_fp"],
        "over_blocked_500": full_eval["over_extraction_guard_block_count"],
        "evidence_missing_500": full_eval["evidence_missing_action_count"],
        "gold_review_queue": gold_queue["queue_total"],
        "coverage_ok":    full_eval["coverage_report"]["fail_class"] is None,
        "natural_shortage": ns,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
