"""evaluator.py — 평가 데이터셋 자동 정확도 측정 (알고리즘 팀 §7-2).

실행 진입점 (단계 6.3):
    from butler_pc_core.card1_extraction.evaluator import run_card1_evaluation, print_report
    report = run_card1_evaluation("tests/card1_extraction/eval_dataset_65.json")
    print_report(report)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── 게이트 기준 (알고리즘 팀 §7-2 정확 기준) ────────────────────────────────

GATE_INTENT_TYPE_ACCURACY     = 0.90   # intent_type 정확도  >= 90%
GATE_DEADLINE_F1              = 0.92   # deadline 추출 F1    >= 92%
GATE_MATERIAL_F1              = 0.90   # material 추출 F1    >= 90%
GATE_ACTION_F1                = 0.90   # action 추출 F1      >= 90%
GATE_FALSE_DEADLINE_RATE      = 0.02   # deadline 환각 비율  <= 2%
GATE_NO_ACTION_FALSE_POSITIVE = 0.03   # 부정형 오탐 비율    <= 3%
GATE_CONFIDENCE_CALIBRATION   = 0.10   # 신뢰도 보정 오차    <= 10%


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────

@dataclass
class CategoryScore:
    category:         str
    total:            int
    correct_intent:   int
    correct_sentence: int
    deadline_f1:      float
    intent_accuracy:  float


@dataclass
class EvalReport:
    total_items: int

    # §7-2 메인 메트릭
    intent_type_accuracy:         float
    sentence_type_accuracy:       float

    deadline_precision:           float
    deadline_recall:              float
    deadline_extraction_f1:       float

    material_precision:           float
    material_recall:              float
    material_extraction_f1:       float

    action_precision:             float
    action_recall:                float
    action_extraction_f1:         float

    false_deadline_rate:          float
    no_action_false_positive:     float
    confidence_calibration_error: float

    # 카테고리별 / 실패 케이스 (기본값 있음 — 선택적)
    category_scores: Dict[str, CategoryScore] = field(default_factory=dict)
    failed_cases:    List[dict]               = field(default_factory=list)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _compute_f1(
    pred_items: List[str],
    gold_items: List[str],
) -> Tuple[float, float, float]:
    """부분 포함 매칭 F1 → (precision, recall, f1).

    양쪽 모두 빈 리스트 → (1.0, 1.0, 1.0).
    pred만 빈 리스트    → (0.0, 0.0, 0.0).
    gold만 빈 리스트    → (0.0, 1.0, 0.0)  [완전 false positive].
    """
    if not gold_items and not pred_items:
        return 1.0, 1.0, 1.0
    if not pred_items:
        return 0.0, 0.0, 0.0
    if not gold_items:
        return 0.0, 1.0, 0.0

    pred_set = set(pred_items)
    gold_set = set(gold_items)

    def _partial(a: str, b: str) -> bool:
        return a in b or b in a

    tp_pred = sum(1 for p in pred_set if any(_partial(p, g) for g in gold_set))
    tp_gold = sum(1 for g in gold_set if any(_partial(g, p) for p in pred_set))

    precision = tp_pred / len(pred_set)
    recall    = tp_gold / len(gold_set)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return round(precision, 4), round(recall, 4), round(f1, 4)


def check_gates(report: EvalReport) -> Dict[str, dict]:
    """
    모든 §7-2 게이트 통과 여부 반환.

    Returns:
        {metric_name: {"value": float, "threshold": float, "passed": bool, "operator": str}}
    """
    return {
        "intent_type_accuracy": {
            "value":     report.intent_type_accuracy,
            "threshold": GATE_INTENT_TYPE_ACCURACY,
            "passed":    report.intent_type_accuracy >= GATE_INTENT_TYPE_ACCURACY,
            "operator":  ">=",
        },
        "deadline_extraction_f1": {
            "value":     report.deadline_extraction_f1,
            "threshold": GATE_DEADLINE_F1,
            "passed":    report.deadline_extraction_f1 >= GATE_DEADLINE_F1,
            "operator":  ">=",
        },
        "material_extraction_f1": {
            "value":     report.material_extraction_f1,
            "threshold": GATE_MATERIAL_F1,
            "passed":    report.material_extraction_f1 >= GATE_MATERIAL_F1,
            "operator":  ">=",
        },
        "action_extraction_f1": {
            "value":     report.action_extraction_f1,
            "threshold": GATE_ACTION_F1,
            "passed":    report.action_extraction_f1 >= GATE_ACTION_F1,
            "operator":  ">=",
        },
        "false_deadline_rate": {
            "value":     report.false_deadline_rate,
            "threshold": GATE_FALSE_DEADLINE_RATE,
            "passed":    report.false_deadline_rate <= GATE_FALSE_DEADLINE_RATE,
            "operator":  "<=",
        },
        "no_action_false_positive": {
            "value":     report.no_action_false_positive,
            "threshold": GATE_NO_ACTION_FALSE_POSITIVE,
            "passed":    report.no_action_false_positive <= GATE_NO_ACTION_FALSE_POSITIVE,
            "operator":  "<=",
        },
        "confidence_calibration_error": {
            "value":     report.confidence_calibration_error,
            "threshold": GATE_CONFIDENCE_CALIBRATION,
            "passed":    report.confidence_calibration_error <= GATE_CONFIDENCE_CALIBRATION,
            "operator":  "<=",
        },
    }


def print_report(report: EvalReport, *, verbose: bool = False) -> None:
    """콘솔 리포트 출력 (단계 6.3 실행용)."""
    gates = check_gates(report)

    def _gate_tag(key: str) -> str:
        g = gates.get(key)
        if g is None:
            return ""
        return "[PASS]" if g["passed"] else "[FAIL]"

    print("\n" + "=" * 64)
    print(f"  카드1 추출 평가 보고서  (총 {report.total_items}건)")
    print("=" * 64)
    print(f"  {'메트릭':<36} {'값':>6}  {'임계값':>6}  결과")
    print("-" * 64)

    rows = [
        ("intent_type_accuracy",        report.intent_type_accuracy,         f">= {GATE_INTENT_TYPE_ACCURACY:.0%}"),
        ("sentence_type_accuracy",      report.sentence_type_accuracy,       "(참고)"),
        ("deadline_extraction_f1",      report.deadline_extraction_f1,       f">= {GATE_DEADLINE_F1:.0%}"),
        ("  deadline_precision",        report.deadline_precision,           ""),
        ("  deadline_recall",           report.deadline_recall,              ""),
        ("material_extraction_f1",      report.material_extraction_f1,       f">= {GATE_MATERIAL_F1:.0%}"),
        ("  material_precision",        report.material_precision,           ""),
        ("  material_recall",           report.material_recall,              ""),
        ("action_extraction_f1",        report.action_extraction_f1,         f">= {GATE_ACTION_F1:.0%}"),
        ("  action_precision",          report.action_precision,             ""),
        ("  action_recall",             report.action_recall,                ""),
        ("false_deadline_rate",         report.false_deadline_rate,          f"<= {GATE_FALSE_DEADLINE_RATE:.0%}"),
        ("no_action_false_positive",    report.no_action_false_positive,     f"<= {GATE_NO_ACTION_FALSE_POSITIVE:.0%}"),
        ("confidence_calibration_error",report.confidence_calibration_error, f"<= {GATE_CONFIDENCE_CALIBRATION:.0%}"),
    ]

    for name, value, note in rows:
        key   = name.strip()
        tag   = _gate_tag(key) if note and note != "(참고)" and not name.startswith("  ") else ""
        print(f"  {name:<36} {value:>6.4f}  {note:<10}  {tag}")

    print("-" * 64)
    failed = [k for k, v in gates.items() if not v["passed"]]
    if not failed:
        print("  모든 §7-2 게이트 통과!")
    else:
        print(f"  FAIL 게이트 ({len(failed)}개): {', '.join(failed)}")

    # 카테고리별 요약
    if report.category_scores:
        print("\n  카테고리별 intent 정확도:")
        for cat, cs in sorted(report.category_scores.items()):
            acc = cs.intent_accuracy
            print(f"    {cat:<20} {cs.correct_intent}/{cs.total}  ({acc:.0%})")

    # 실패 케이스 (verbose 모드)
    if verbose and report.failed_cases:
        print(f"\n  실패 케이스 ({len(report.failed_cases)}건) — 상위 10건:")
        for case in report.failed_cases[:10]:
            print(f"    [{case['id']}] {case['category']}")
            print(f"      텍스트: {case['source_text'][:55]}...")
            print(f"      intent: gold={case['gold_intent']}  pred={case['pred_intent']}  "
                  f"{'OK' if case['intent_ok'] else 'FAIL'}")

    print("=" * 64 + "\n")


def run_card1_evaluation(
    dataset_path: str,
    use_llm: bool = False,
    output_json: Optional[str] = None,
    verbose: bool = False,
) -> EvalReport:
    """
    JSON 데이터셋 파일 → EvalReport.

    단계 6.3에서 실제 실행. use_llm=False 기본값으로 SKIP_LLM 자동 적용.
    """
    if not use_llm:
        os.environ["SKIP_LLM"] = "true"

    # 로컬 임포트 — 모듈 로드 시 LLM 연결 방지
    from butler_pc_core.card1_extraction import extract_card1  # noqa: PLC0415

    with open(dataset_path, encoding="utf-8") as f:
        raw = json.load(f)
    items: List[dict] = raw["items"] if isinstance(raw, dict) else raw

    total = len(items)
    intent_correct = sentence_correct = 0

    # Deadline binary TP/FP/FN
    dl_tp = dl_fp = dl_fn = dl_tn = 0

    # Materials / Actions 누적 TP/FP/FN (부분 포함 매칭)
    mt_tp = mt_fp = mt_fn = 0
    ac_tp = ac_fp = ac_fn = 0

    false_deadline_count = null_deadline_total = 0
    no_action_gold_total = no_action_fp_count  = 0

    calibration_errors: List[float] = []
    failed_cases: List[dict]        = []
    cat_accum: Dict[str, dict]      = {}

    for item in items:
        item_id  = item["id"]
        category = item["category"]
        text     = item["source_text"]
        expected = item["expected"]

        result = extract_card1(text, use_llm=use_llm)

        # ── intent_type ──────────────────────────────────────────────────────
        gold_intent = expected["intent_type"].lower()
        pred_intent = result.intent_type.value
        intent_ok   = (pred_intent == gold_intent)
        if intent_ok:
            intent_correct += 1

        # ── sentence_type ────────────────────────────────────────────────────
        gold_sent = expected["sentence_type"].upper()
        pred_sent = result.sentence_type.name.upper()
        sent_ok   = (pred_sent == gold_sent)
        if sent_ok:
            sentence_correct += 1

        # ── deadline ─────────────────────────────────────────────────────────
        gold_deadline = expected["deadline"]
        gold_has      = gold_deadline is not None
        pred_raw      = result.deadline_raw or None
        pred_has      = pred_raw is not None

        if gold_has and pred_has:
            dl_tp += 1
        elif gold_has and not pred_has:
            dl_fn += 1
        elif not gold_has and pred_has:
            dl_fp += 1
            false_deadline_count += 1
        else:
            dl_tn += 1

        if not gold_has:
            null_deadline_total += 1

        # ── materials ────────────────────────────────────────────────────────
        gold_mats = expected.get("materials", [])
        pred_mats = result.materials

        if not gold_mats and not pred_mats:
            mt_tp += 1
        else:
            gs = set(gold_mats)
            ps = set(pred_mats)
            for pm in ps:
                if any(pm in gm or gm in pm for gm in gs):
                    mt_tp += 1
                else:
                    mt_fp += 1
            for gm in gs:
                if not any(pm in gm or gm in pm for pm in ps):
                    mt_fn += 1

        # ── actions ──────────────────────────────────────────────────────────
        gold_acts = [a["action_text"] for a in expected.get("actions", [])]
        pred_acts = [a.action_text for a in result.actions]

        if not gold_acts and not pred_acts:
            ac_tp += 1
        else:
            gs_a = set(gold_acts)
            ps_a = set(pred_acts)
            for pa in ps_a:
                if any(pa in ga or ga in pa for ga in gs_a):
                    ac_tp += 1
                else:
                    ac_fp += 1
            for ga in gs_a:
                if not any(pa in ga or ga in pa for pa in ps_a):
                    ac_fn += 1

        # ── no_action 오탐 ────────────────────────────────────────────────────
        if gold_intent == "no_action":
            no_action_gold_total += 1
            if result.actions:
                no_action_fp_count += 1

        # ── confidence calibration (MAE) ─────────────────────────────────────
        binary_acc = (int(intent_ok) + int(sent_ok)) / 2.0
        calibration_errors.append(abs(result.confidence - binary_acc))

        # ── 카테고리 누적 ─────────────────────────────────────────────────────
        if category not in cat_accum:
            cat_accum[category] = {
                "total": 0, "intent_ok": 0, "sent_ok": 0,
                "dl_tp": 0, "dl_fp": 0, "dl_fn": 0,
            }
        c = cat_accum[category]
        c["total"]     += 1
        c["intent_ok"] += int(intent_ok)
        c["sent_ok"]   += int(sent_ok)
        c["dl_tp"]     += int(gold_has and pred_has)
        c["dl_fp"]     += int(not gold_has and pred_has)
        c["dl_fn"]     += int(gold_has and not pred_has)

        # ── 실패 케이스 기록 ─────────────────────────────────────────────────
        if not intent_ok or (gold_has and not pred_has):
            failed_cases.append({
                "id":           item_id,
                "category":     category,
                "source_text":  text,
                "gold_intent":  gold_intent,
                "pred_intent":  pred_intent,
                "intent_ok":    intent_ok,
                "gold_deadline": gold_deadline,
                "pred_deadline": pred_raw,
            })

    # ── 최종 메트릭 산출 ──────────────────────────────────────────────────────

    def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
        p = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return round(p, 4), round(r, 4), round(f, 4)

    dl_p, dl_r, dl_f = _prf(dl_tp, dl_fp, dl_fn)
    mt_p, mt_r, mt_f = _prf(mt_tp, mt_fp, mt_fn)
    ac_p, ac_r, ac_f = _prf(ac_tp, ac_fp, ac_fn)

    fdr = false_deadline_count / null_deadline_total if null_deadline_total > 0 else 0.0
    nfp = no_action_fp_count   / no_action_gold_total if no_action_gold_total > 0 else 0.0
    cal = sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0

    # ── 카테고리 스코어 ────────────────────────────────────────────────────────
    cat_scores: Dict[str, CategoryScore] = {}
    for name, c in cat_accum.items():
        n   = c["total"]
        p_c = c["dl_tp"] / (c["dl_tp"] + c["dl_fp"]) if (c["dl_tp"] + c["dl_fp"]) > 0 else 1.0
        r_c = c["dl_tp"] / (c["dl_tp"] + c["dl_fn"]) if (c["dl_tp"] + c["dl_fn"]) > 0 else 1.0
        f_c = 2 * p_c * r_c / (p_c + r_c) if (p_c + r_c) > 0 else 0.0
        cat_scores[name] = CategoryScore(
            category        = name,
            total           = n,
            correct_intent  = c["intent_ok"],
            correct_sentence= c["sent_ok"],
            deadline_f1     = round(f_c, 4),
            intent_accuracy = round(c["intent_ok"] / n, 4),
        )

    report = EvalReport(
        total_items               = total,
        intent_type_accuracy      = round(intent_correct / total, 4),
        sentence_type_accuracy    = round(sentence_correct / total, 4),
        deadline_precision        = dl_p,
        deadline_recall           = dl_r,
        deadline_extraction_f1    = dl_f,
        material_precision        = mt_p,
        material_recall           = mt_r,
        material_extraction_f1    = mt_f,
        action_precision          = ac_p,
        action_recall             = ac_r,
        action_extraction_f1      = ac_f,
        false_deadline_rate       = round(fdr, 4),
        no_action_false_positive  = round(nfp, 4),
        confidence_calibration_error = round(cal, 4),
        category_scores           = cat_scores,
        failed_cases              = failed_cases,
    )

    if output_json:
        _write_json_report(report, output_json)

    if verbose:
        print_report(report, verbose=True)

    return report


def _write_json_report(report: EvalReport, path: str) -> None:
    import dataclasses
    data = dataclasses.asdict(report)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
