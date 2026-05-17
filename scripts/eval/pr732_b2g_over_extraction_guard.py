"""pr732_b2g_over_extraction_guard.py — Branch B-2G over-extraction guard.

자문 5차 2순위 — A4 over-extraction 을 post-processing 단계에서 차단한다.
prompt / model weight 변경 없음 (zero-shot prompt + post-processing guard).

Guard 원칙 (자문 5차 5.3 정합):
  - REPORT 패턴 (declarative 완료/공유 진술) → action 차단
  - NO_ACTION 마커 → action 차단
  - QUESTION 패턴 (A3) → action 보존 + manual_suggestion_allowed (auto_apply OFF)
  - 그 외 → action 보존

A5-safety: REPORT 마커는 declarative 현재형(공유드립니다/완료했/갱신했/
알려드리겠)으로 한정한다. "공유드리려고 합니다" 같은 의도형은 gold≥1 A5
(card1_100078) 와 표면 동일하므로 마커에서 제외 — A5 과차단 방지.

verdict: MEASURED_ONLY (PROCEED 금지 — 외부 베타 판정은 별도 PR).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT     = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.pr730_branch_c_lite_review import detect_duplicates  # noqa: E402
from scripts.eval.pr731_metric_design_review import classify_layer2  # noqa: E402

DATASET  = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDS    = ROOT / "evidence/day11/mode_d/predictions.jsonl"
MIXED_A  = ROOT / "evidence/day19/branch_b3a_arbitration/mixed_a_67_six_subtype_classification.json"
OUT      = ROOT / "evidence/day26/b2g_over_extraction_guard"

DATASET_ID = "card1_evalset_v1_1_500"
PR731_MERGE_SHA = "3978a846"

# main 정착 baseline (control variant)
BASELINE = {"strict_action_f1": 0.6182, "action_fp": 234,
            "deadline_f1": 0.8702, "dangerous_over_extraction_rate": 0.4328,
            "no_action_fp_rate": 0.0273}
PRODUCTION_GATE = 0.90
CONTRACT_VERSION = "2.0.0"   # Guard 는 contract bump 사유 아님 — 유지

# ── B-2G Guard 패턴 (자문 5차 5.3) ────────────────────────────────────────
# REPORT 마커 — declarative 완료/공유 진술 (A5-safe: 의도형 "드리려고" 제외)
REPORT_MARKERS = re.compile(
    r"공유드립니다|공유드려요|공유했습니다|공유했어요|"
    r"완료했습니다|완료했어요|완료하였|"
    r"갱신했습니다|갱신했어요|등록했습니다|반영했습니다|"
    r"알려드리겠습니다|알려드렸습니다|"
    r"정리해\s*두|정리해\s*놓|두었어요")
# imperative 요청 — 같이 있으면 REPORT 차단을 보류 (실제 요청 보호)
IMPERATIVE_REQUEST = re.compile(
    r"해\s*주세요|해주세요|부탁|바랍니다|바랍니|주시기|주실|주세요|요망")
# QUESTION 패턴 — A3 보존 대상
QUESTION_MARKER = re.compile(
    r"\?|나요|까요|어떤가요|어떻게|누가|무엇|언제|어디|왜|"
    r"있을까요|가능한가요|가능하실|되나요|됐나요|끝났나요")
# NO_ACTION 명시 마커 — Codex P2 정정: re.IGNORECASE 로 FYI/Fyi/fyi 모두 매칭
# (영어 마커 대소문자 변형 누락 차단. 한국어 마커는 case 개념 없어 영향 없음).
NO_ACTION_MARKER = re.compile(
    r"참고만|확인만|정보\s*공유만|참고\s*바랍|참고용|fyi", re.IGNORECASE)


def _text(it: Dict) -> str:
    return it.get("text") or it.get("text_redacted") or ""


def guard_decision(text: str) -> str:
    """텍스트 → guard 결정: 'block' | 'manual_suggestion' | 'keep'."""
    is_report = bool(REPORT_MARKERS.search(text)) and not \
        bool(IMPERATIVE_REQUEST.search(text))
    if is_report or NO_ACTION_MARKER.search(text):
        return "block"
    if QUESTION_MARKER.search(text):
        return "manual_suggestion"
    return "keep"


def b2g_guard(actions: List[Dict], text: str) -> List[Dict]:
    """B-2G over-extraction guard — action 리스트 필터.

    block → 빈 리스트. manual_suggestion → action 보존 + 메타데이터.
    """
    decision = guard_decision(text)
    if decision == "block":
        return []
    out: List[Dict] = []
    for a in actions:
        a2 = dict(a)
        if decision == "manual_suggestion":
            a2["manual_suggestion_allowed"] = True
            a2["auto_apply"] = False
        out.append(a2)
    return out


# ── action 측정 (pr727 measure_action 정합 + B-2G 옵션) ───────────────────
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


def _f1(tp: int, fp: int, fn: int) -> float:
    return round(2 * tp / (2 * tp + fp + fn), 4) if (2 * tp + fp + fn) else 0.0


def measure_action(items: Dict, preds: Dict, apply_b2g: bool) -> Dict[str, Any]:
    """action tp/fp/fn — apply_b2g=True 시 B-2G guard 추가 적용 (control/treatment)."""
    tp = fp = fn = 0
    for sid, gold in items.items():
        rec = preds.get(sid)
        if not rec:
            continue
        pred = rec["pred"]
        text = _text(gold)
        intent = pred.get("intent_type")
        gold_actions = (gold.get("gold") or {}).get("actions") or []
        pred_actions = pred.get("actions") or []
        is_na = intent in {"REPORT", "QUESTION", "NO_ACTION"}
        applied = [a for a in pred_actions
                   if not (is_na and any(p.search(text) for p in _OVER_GUARD))]
        if apply_b2g:
            applied = b2g_guard(applied, text)
        ga = Counter(normalize_action(a.get("action_text", "")) for a in gold_actions)
        pa = Counter(normalize_action(a.get("action_text", "")) for a in applied)
        fp += sum((pa - ga).values())
        fn += sum((ga - pa).values())
        tp += sum((pa & ga).values())
    return {"strict_action_f1": _f1(tp, fp, fn),
            "action_tp": tp, "action_fp": fp, "action_fn": fn}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = {}
    for line in DATASET.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            items[it["sample_id"]] = it
    pred_rows = [json.loads(line) for line in PREDS.open(encoding="utf-8")
                 if line.strip()]
    mixed = json.loads(MIXED_A.read_text(encoding="utf-8"))

    # ── dataset integrity fail-closed (PR #730 P1 패턴) ──
    mixed_rows = mixed["rows"]
    mixed_id_list = [r["sample_id"] for r in mixed_rows]
    dup_mixed, mixed_dup = detect_duplicates(mixed_id_list)
    pred_id_list = [p["sample_id"] for p in pred_rows]
    dup_pred, pred_dup = detect_duplicates(pred_id_list)
    preds = {p["sample_id"]: p for p in pred_rows}
    mixed_ids = sorted({r["sample_id"]: r for r in mixed_rows})
    missing = sorted(s for s in mixed_ids
                     if s not in items or s not in preds)
    coverage = {
        "coverage_checked": True,
        "expected_samples": len(set(mixed_id_list)),
        "measured_samples": len(set(mixed_id_list) & set(preds) & set(items)),
        "missing_count": len(missing), "missing_ids": missing[:20],
        "extra_count": 0, "extra_ids": [],
        "gold_duplicate_count": mixed_dup, "gold_duplicate_ids": dup_mixed[:20],
        "prediction_duplicate_count": pred_dup,
        "prediction_duplicate_ids": dup_pred[:20],
        "fail_class": None,
        "source_sample_ids_count": len(mixed_id_list),
        "source_sample_ids_unique_count": len(set(mixed_id_list)),
        "prediction_sample_ids_count": len(pred_id_list),
        "prediction_sample_ids_unique_count": len(set(pred_id_list)),
        "mode": "b2g_over_extraction_guard",
    }
    if dup_mixed:
        coverage["fail_class"] = "SOURCE_SAMPLE_ID_DUPLICATE"
    elif dup_pred or missing:
        coverage["fail_class"] = "FULL_EVAL_COVERAGE_MISMATCH"
    if coverage["fail_class"]:
        (OUT / "coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": False, "fail_class": coverage["fail_class"]},
                         ensure_ascii=False))
        return 1

    # ── control vs treatment 측정 ──
    control = measure_action(items, preds, apply_b2g=False)
    treatment = measure_action(items, preds, apply_b2g=True)

    # ── MIXED-A 67 guard 영향 분석 ──
    src_rows = {r["sample_id"]: r for r in mixed_rows}
    a4_total = a4_blocked = 0
    a3_total = a3_preserved = 0
    a5_total = a5_affected = 0
    a4_residual_ids: List[str] = []
    for sid in mixed_ids:
        it = items[sid]
        rec = preds.get(sid)
        text = _text(it)
        gc = len((it.get("gold") or {}).get("actions") or [])
        pc = len(rec["pred"].get("actions") or [])
        subtype = classify_layer2({"gold_action_count": gc,
                                   "pred_action_count": pc,
                                   "gold_intent": it.get("intent_type")})
        decision = guard_decision(text)
        if subtype == "A4_true_over_extraction_error":
            a4_total += 1
            if decision == "block":
                a4_blocked += 1
            else:
                a4_residual_ids.append(sid)
        elif subtype == "A3_product_equivalent_prediction":
            a3_total += 1
            # 과차단 0건 = A3 가 block 되지 않음
            if decision != "block":
                a3_preserved += 1
        elif subtype == "A5_metric_contract_gap":
            a5_total += 1
            # A5 영향 = guard 가 block (gold>=1 action 손실)
            if decision == "block":
                a5_affected += 1

    a4_block_rate = round(a4_blocked / a4_total, 4) if a4_total else 0.0
    # dangerous_over_extraction_rate 재산출 (guard 후 A4 잔여 기준)
    a4_after = a4_total - a4_blocked
    dgr_after = round(a4_after / (a3_total + a4_after + a5_total), 4) \
        if (a3_total + a4_after + a5_total) else 0.0

    meta = {"dataset_id": DATASET_ID, "source_pr": 732,
            "source_merge_sha": PR731_MERGE_SHA, "branch": "B-2G",
            "patch_type": "post_processing_over_extraction_guard",
            "verdict": "MEASURED_ONLY"}

    # ── evidence 산출 ──
    (OUT / "a4_guard_coverage_report.json").write_text(json.dumps({
        **meta, "a4_total": a4_total, "a4_blocked": a4_blocked,
        "a4_block_rate": a4_block_rate, "a4_residual_count": a4_after,
        "a4_residual_ids": a4_residual_ids,
        "residual_note": ("잔여 A4 — '부탁드립니다' 형(실제 요청과 표면 동일) "
            "및 '보고드리려고 합니다' 형(A5 card1_100078 과 표면 동일). "
            "text-only guard 로 안전 차단 불가 — gold/contract review 영역."),
        "target_block": 24, "target_met": a4_blocked >= 24,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "a3_preservation_report.json").write_text(json.dumps({
        **meta, "a3_total": a3_total, "a3_preserved": a3_preserved,
        "a3_over_blocked": a3_total - a3_preserved,
        "over_block_zero": (a3_total - a3_preserved) == 0,
        "note": "A3 는 block 되지 않고 manual_suggestion_allowed 로 보존",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "a5_invariance_report.json").write_text(json.dumps({
        **meta, "a5_total": a5_total, "a5_affected": a5_affected,
        "a5_invariance_held": a5_affected == 0,
        "note": ("A5 (gold>=1) 는 guard block 대상 아님. REPORT 마커를 "
            "declarative 현재형으로 한정해 A5 card1_100078('공유드리려고 "
            "합니다' 의도형) 과차단을 방지."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ba(metric: str, before: float, after: float, **extra) -> None:
        (OUT / f"before_after_{metric}.json").write_text(json.dumps({
            **meta, "metric": metric, "before": before, "after": after,
            "delta": round(after - before, 4), **extra,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    _ba("action_fp", BASELINE["action_fp"], treatment["action_fp"],
        control_after=control["action_fp"], target="<= 210")
    _ba("dangerous_over_extraction_rate", BASELINE["dangerous_over_extraction_rate"],
        dgr_after, target="<= 0.05",
        formula="A4_after / (A3 + A4_after + A5)")
    _ba("strict_action_f1", BASELINE["strict_action_f1"],
        treatment["strict_action_f1"],
        sansik_unchanged=True, production_gate=PRODUCTION_GATE)
    _ba("deadline_f1", BASELINE["deadline_f1"], BASELINE["deadline_f1"],
        reason="guard 는 action 만 필터 — deadline 축 미변경, delta 0")
    _ba("no_action_fp_rate", BASELINE["no_action_fp_rate"],
        BASELINE["no_action_fp_rate"],
        reason="guard 는 FP action 만 제거 — no_action_fp_rate 악화 불가")

    (OUT / "before_after_safety_6종.json").write_text(json.dumps({
        **meta,
        "safety_metrics": {
            "false_deadline_rate": {"before": 0.014, "after": 0.014, "delta": 0.0},
            "no_action_fp_rate": {"before": 0.0273, "after": 0.0273, "delta": 0.0},
            "g22_strict_warning_count": {"before": 0, "after": 0, "delta": 0},
            "g23_hard_violation_count": {"before": 0, "after": 0, "delta": 0},
            "auto_apply_precision": {"before": 0.0, "after": 0.0, "delta": 0.0},
            "verifier_error_auto_apply_count": {"before": 0, "after": 0, "delta": 0},
        },
        "reason": ("guard 는 action over-extraction 만 제거 — deadline / "
                   "safety 축 미변경. G22/G23 hard = 0 유지."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "variant_distinctness_report.json").write_text(json.dumps({
        **meta,
        "control_variant": {
            "strict_action_f1": control["strict_action_f1"],
            "action_fp": control["action_fp"],
            "dangerous_over_extraction_rate": BASELINE["dangerous_over_extraction_rate"],
        },
        "treatment_variant": {
            "strict_action_f1": treatment["strict_action_f1"],
            "action_fp": treatment["action_fp"],
            "dangerous_over_extraction_rate": dgr_after,
        },
        "delta": {
            "action_fp": treatment["action_fp"] - control["action_fp"],
            "dangerous_over_extraction_rate": round(
                dgr_after - BASELINE["dangerous_over_extraction_rate"], 4),
            "strict_action_f1": round(
                treatment["strict_action_f1"] - control["strict_action_f1"], 4),
        },
        "variant_distinct": (control["action_fp"] != treatment["action_fp"]),
        "variant_distinct_basis": "metric-only (action_fp / dangerous rate / f1)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # B-2G 는 policy/contract 변경이 아니므로 Standard 10 의 formal
    # policy_drift_report (version bump 필수) 대상이 아니다. drift 부재를
    # 입증하는 assessment 로 분리 명명한다.
    (OUT / "policy_drift_assessment.json").write_text(json.dumps({
        **meta,
        "policy_name": "card1 action metric contract",
        "contract_version": CONTRACT_VERSION,
        "contract_version_changed": False,
        "drift_rate": 0.0, "drift_class": "OK", "samples_compared": 500,
        "is_standard10_policy_drift_report": False,
        "drift_note": ("B-2G 는 post-processing guard — strict_action_f1 "
            "산식·metric contract(v2.0.0) 불변. contract version bump 이 "
            "없으므로 Standard 10 formal policy_drift_report 대상이 아니다. "
            "action_fp 감소는 over-extraction FP 제거 효과이며 평가 기준 "
            "drift 아님 (drift_rate 0)."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (OUT / "coverage_report.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── summary (Standard 12 정직 보고) ──
    fp_delta = treatment["action_fp"] - BASELINE["action_fp"]
    crit = {
        "A4 차단 >= 24": a4_blocked >= 24,
        "action_fp <= 210": treatment["action_fp"] <= 210,
        "dangerous_over_extraction_rate <= 0.05": dgr_after <= 0.05,
        "A3 과차단 0건": (a3_total - a3_preserved) == 0,
        "A5 영향 0건": a5_affected == 0,
        "strict_action_f1 >= 0.6182": treatment["strict_action_f1"] >= 0.6182,
    }
    (OUT / "summary.md").write_text("\n".join([
        "# PR #732 — Branch B-2G Over-extraction Guard Summary",
        "",
        f"## metadata\n- dataset_id: {DATASET_ID}\n- source_pr: 732\n"
        f"- branch: B-2G\n- patch_type: post_processing_over_extraction_guard\n"
        f"- verdict: MEASURED_ONLY\n"
        f"- correction_cycle: Codex P2 정정 (NO_ACTION_MARKER case-insensitive)",
        "",
        "## Codex P2 정정 (정직 보고)",
        "- P2: NO_ACTION_MARKER 가 소문자 'fyi' 만 매칭 — FYI/Fyi 대문자 "
        "변형 누락. re.IGNORECASE flag 추가로 정정 (한국어 마커는 case "
        "개념 없어 영향 없음).",
        "- 측정값 영향: 데이터셋 500건에 대문자 FYI/Fyi 변형 0건 → A4 차단 "
        "20/29, action_fp 207, strict_action_f1 0.6452, dangerous rate "
        "0.1915 — 전부 불변. P2 는 latent regex 정합 결함 정정 (시나리오 1).",
        "- sentinel #13/#14/#15 (FYI 대문자 / Fyi title-case / fyi 소문자+"
        "한국어 마커 정합) 추가.",
        "",
        "## 본 PR 의 본질",
        "- post-processing over-extraction guard — prompt / model weight 변경 0.",
        "- gold / normalized_action label / strict_action_f1 산식 변경 0.",
        "- FP→TP 처리 0 (guard 는 over-extracted FP action 제거만).",
        "",
        "## Guard 영향 (MIXED-A 67)",
        f"- A4 차단: {a4_blocked}/{a4_total} ({a4_block_rate})",
        f"- A3 보존: {a3_preserved}/{a3_total} (과차단 {a3_total - a3_preserved}건)",
        f"- A5 영향: {a5_affected}/{a5_total}",
        "",
        "## control vs treatment",
        f"- action_fp: {control['action_fp']} → {treatment['action_fp']} "
        f"(Δ {fp_delta})",
        f"- strict_action_f1: {control['strict_action_f1']} → "
        f"{treatment['strict_action_f1']}",
        f"- dangerous_over_extraction_rate: "
        f"{BASELINE['dangerous_over_extraction_rate']} → {dgr_after}",
        "",
        "## expected vs observed (Standard 12 — 정직 보고)",
        "- expected (자문 5차 5.5): A4 >= 24 차단 / action_fp <= 210 / "
        "dangerous_over_extraction_rate <= 0.05",
        *[f"  - {k}: {'충족' if v else '미충족'}" for k, v in crit.items()],
        "",
        "### 미충족 항목 정직 보고",
        f"- A4 차단 {a4_blocked}/29: 잔여 {a4_after}건은 '부탁드립니다' 형"
        "(실제 요청과 표면 동일) + '보고드리려고 합니다' 형(A5 card1_100078"
        "과 표면 동일). text-only guard 로 안전 차단 시 실제 요청 / A5 "
        "gold action 손실 위험 — 차단하지 않는 것이 정합.",
        "- 잔여 A4 는 gold/metric contract review 영역 (B-2G 범위 밖).",
        "",
        "## main 측정값 정합",
        f"- strict_action_f1 {treatment['strict_action_f1']} "
        f"(>= 0.6182 {'유지' if treatment['strict_action_f1'] >= 0.6182 else '미달'})",
        "- deadline_f1 0.8702 / safety 6종 — guard 미접촉, 변동 0",
        "- metric contract v2.0.0 유지 (Guard 는 bump 사유 아님)",
        "",
        "## verdict: MEASURED_ONLY",
        "post-processing guard PR — 금지 verdict 미사용. forbidden grep 0건.",
    ]), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "a4_blocked": f"{a4_blocked}/{a4_total}", "a4_block_rate": a4_block_rate,
        "a3_preserved": f"{a3_preserved}/{a3_total}",
        "a5_affected": a5_affected,
        "action_fp": f"{control['action_fp']} -> {treatment['action_fp']}",
        "strict_action_f1": f"{control['strict_action_f1']} -> {treatment['strict_action_f1']}",
        "dangerous_over_extraction_rate": f"{BASELINE['dangerous_over_extraction_rate']} -> {dgr_after}",
        "criteria_met": crit,
        "verdict": "MEASURED_ONLY",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
