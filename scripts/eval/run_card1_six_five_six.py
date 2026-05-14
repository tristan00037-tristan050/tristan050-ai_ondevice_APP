"""run_card1_six_five_six.py — 6.5.6 Day 11 4 mode 평가 실행기.

알고리즘 팀 Day 11 명세 (2026-05-14):
  Mode A: parser only (heuristic)
  Mode B: Qwen3-4B only (parser hint 없음)
  Mode C: parser + Qwen3-4B (hint 적용)
  Mode D: parser + Qwen3-4B + verifier (card1 V1~V10) + calibrator (frozen)

산출:
  evidence/day11/mode_{a,b,c,d}/run_config.json
  evidence/day11/mode_{a,b,c,d}/predictions.jsonl
  evidence/day11/mode_{a,b,c,d}/metrics_13.json
  evidence/day11/mode_{a,b,c,d}/run.log
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# repo root to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction import extract_card1  # noqa
from butler_pc_core.card1_extraction.llm_extractor import (  # noqa
    extract_with_llm_v1,
)
from butler_pc_core.card1_extraction.parser import (  # noqa
    classify_sentence_type, extract_actions_candidates,
    extract_deadlines, extract_materials,
)
from scripts.eval.verifier_card1 import (  # noqa
    apply_card1_hard_rules, _g23_hard_violation, _has_action_verb,
)

INTENT_GOLD_TO_PRED = {
    # gold 5분류 → 평가 4분류 호환 매핑 (가이드 §3 INTENT_COMPAT_MAP_V1)
    # 비교는 운영 호환 4분류 기준 (QUESTION → NO_ACTION + answer_required)
    # 단, 우리는 5분류 그대로 비교 (메인 팀 G5 영역과 동일).
}

INTENT_LLM_TO_GOLD = {
    "request":     "REQUEST",
    "command":     "COMMAND",
    "instruction": "COMMAND",
    "report":      "REPORT",
    "no_action":   "NO_ACTION",
    "question":    "QUESTION",
    "schedule":    "REQUEST",
    "other":       "NO_ACTION",
    "unknown":     "NO_ACTION",
}

SAFE_INTENT_AUTO = {"REQUEST", "REPORT", "NO_ACTION"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _heuristic_intent(text: str, sent_type: str, actions: List[str]) -> str:
    """parser-only intent 추정 (Mode A)."""
    if sent_type == "NEGATIVE":
        return "NO_ACTION"
    # PURE_QUESTION 어미
    if any(p in text for p in ["어떻게 되나요", "언제인가요", "누구인가요", "어디인가요",
                                "언제죠", "어디에", "누가 담당"]):
        return "QUESTION"
    # REPORT 어미
    if any(p in text for p in ["완료했습니다", "보고드립니다", "안내드립니다",
                                "공유했습니다", "전달했습니다", "보고드려요"]):
        return "REPORT"
    # COMMAND 어미
    if any(p in text for p in ["하세요", "하시기 바랍니다", "하시라"]):
        return "COMMAND"
    # action verbs 존재 + 요청형
    if actions or _has_action_verb(text):
        return "REQUEST"
    return "NO_ACTION"


def _heuristic_deadline_type(text: str, deadlines: List[str]) -> Tuple[str, bool]:
    if not deadlines and not any(p in text for p in ["까지", "안에", "이내", "이전"]):
        return "NONE", False
    if any(p in text for p in ["지금", "즉시", "ASAP", "바로", "긴급"]):
        return "URGENCY", False
    if any(p in text for p in ["완료되면", "확인되면", "수정이 끝나면"]):
        return "CONDITION", False
    if any(p in text for p in ["언제까지", "기한이", "마감이 언제"]):
        return "INQUIRY", False
    if any(p in text for p in ["오늘", "이번 주", "다음 주", "이번 달"]):
        return "SOFT", True
    return "HARD", True


def _mode_a_predict(text: str) -> Dict[str, Any]:
    """Mode A: parser only — heuristic intent/deadline/actions."""
    deadlines = extract_deadlines(text)
    actions   = extract_actions_candidates(text)
    materials = extract_materials(text)
    sent_type = classify_sentence_type(text)

    intent = _heuristic_intent(text, sent_type, actions)
    dtype, dact = _heuristic_deadline_type(text, deadlines)

    if intent == "QUESTION":
        action_required, answer_required = False, True
    elif intent == "REPORT":
        action_required, answer_required = False, False
    elif intent == "NO_ACTION":
        action_required, answer_required = False, False
    elif intent == "COMMAND":
        action_required, answer_required = True, False
    else:  # REQUEST
        action_required, answer_required = True, True

    out_actions = [{"action_text": a, "evidence": a} for a in actions[:5]]
    if intent == "NO_ACTION":
        out_actions = []

    return {
        "intent_type":            intent,
        "deadline_type":          dtype,
        "deadline_is_actionable": dact,
        "action_required":        action_required,
        "answer_required":        answer_required,
        "auto_apply_allowed":     False,
        "actions":                out_actions,
        "materials":              materials[:5],
        "schema_valid":           True,
        "base_verifier_errors":   [],
        "raw_intent_confidence":  0.5,  # heuristic = mid
        "raw_action_confidence":  0.5,
    }


def _llm_predict(
    text: str, hints: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mode B/C: LLM 추출. hints=None → Mode B, dict → Mode C."""
    try:
        result = extract_with_llm_v1(text, parsed_hints=hints)
        extraction = result.extraction
        schema_valid = result.schema_valid
    except Exception as e:
        return {
            "intent_type":            "NO_ACTION",
            "deadline_type":          "NONE",
            "deadline_is_actionable": False,
            "action_required":        False,
            "answer_required":        False,
            "auto_apply_allowed":     False,
            "actions":                [],
            "materials":              [],
            "schema_valid":           False,
            "base_verifier_errors":   [f"llm_error:{type(e).__name__}"],
            "raw_intent_confidence":  0.0,
            "raw_action_confidence":  0.0,
        }

    # extraction.intent_type 는 IntentType enum
    raw_intent = extraction.intent_type.value if extraction.intent_type else "unknown"
    intent = INTENT_LLM_TO_GOLD.get(raw_intent, "NO_ACTION")

    # deadline_type 추정: extraction.deadline_raw + 텍스트 기반 보완
    if extraction.deadline_raw:
        if any(p in text for p in ["언제까지", "기한이 어떻게"]):
            dtype, dact = "INQUIRY", False
        elif any(p in text for p in ["지금", "즉시", "바로", "긴급"]):
            dtype, dact = "URGENCY", False
        elif any(p in text for p in ["완료되면", "확인되면"]):
            dtype, dact = "CONDITION", False
        elif any(p in text for p in ["오늘", "이번 주", "다음 주", "이번 달"]):
            dtype, dact = "SOFT", True
        else:
            dtype, dact = "HARD", True
    else:
        dtype, dact = "NONE", False

    if intent == "QUESTION":
        action_required, answer_required = False, True
    elif intent == "REPORT":
        action_required, answer_required = False, False
    elif intent == "NO_ACTION":
        action_required, answer_required = False, False
    elif intent == "COMMAND":
        action_required, answer_required = True, False
    else:  # REQUEST
        action_required, answer_required = True, True

    out_actions = []
    for a in extraction.actions[:5]:
        out_actions.append({
            "action_text": a.action_text,
            "evidence":    a.source_evidence,
            "confidence":  float(a.confidence or 0.0),
        })

    base_errors: List[str] = []
    if not schema_valid:
        base_errors.append("schema_invalid")
    # evidence in source check
    for i, a in enumerate(out_actions):
        if a["evidence"] and a["evidence"] not in text:
            base_errors.append(f"action[{i}].evidence_not_in_source")
    for m in extraction.materials:
        if m and m not in text:
            base_errors.append(f"material '{m}' not in source")

    return {
        "intent_type":            intent,
        "deadline_type":          dtype,
        "deadline_is_actionable": dact,
        "action_required":        action_required,
        "answer_required":        answer_required,
        "auto_apply_allowed":     False,  # base 단계에서는 false, mode D 에서 결정
        "actions":                out_actions,
        "materials":              extraction.materials[:5],
        "schema_valid":           schema_valid,
        "base_verifier_errors":   base_errors,
        "raw_intent_confidence":  float(extraction.confidence or 0.5),
        "raw_action_confidence":  float(extraction.confidence or 0.5),
    }


def _platt_sigmoid(z: float, A: float, B: float) -> float:
    """Platt sigmoid: 1 / (1 + exp(A*z + B))."""
    return 1.0 / (1.0 + math.exp(A * z + B))


def _apply_calibration(pred: Dict[str, Any], calibrator: Dict[str, Any]) -> None:
    """frozen Platt sigmoid 적용 — pred 에 calibrated_* 필드 추가.

    Codex P1-1 정정 (옵션 A): intent → intent Platt, action → action Platt
    매핑 정합. swap 금지.
    """
    targets = calibrator.get("targets", {}) if calibrator else {}
    intent  = targets.get("intent", {})
    action  = targets.get("action", {})
    pred["intent_confidence_calibrated"] = _platt_sigmoid(
        pred.get("raw_intent_confidence", 0.0),
        intent.get("A", -4.0), intent.get("B", 2.0),
    )
    pred["action_confidence_calibrated"] = _platt_sigmoid(
        pred.get("raw_action_confidence", 0.0),
        action.get("A", -4.0), action.get("B", 2.0),
    )


def _mode_d_compute_auto_candidate(
    pred: Dict[str, Any], calibrator: Dict[str, Any],
) -> bool:
    """Codex P1-2 정정 (옵션 B+C): auto_apply candidate 산출 (verifier 호출 전).

    조건:
      - calibrated intent confidence ≥ threshold.intent
      - calibrated action confidence ≥ threshold.action
      - intent_type ∈ {REQUEST, COMMAND} (action 발생 클래스)
      - action_required = true
    위험 작업 / safe class 검증은 verifier_card1 V8/V9 에서 수행.
    """
    thr_obj = (calibrator or {}).get("auto_apply_threshold", {})
    if isinstance(thr_obj, dict):
        thr_intent = float(thr_obj.get("intent", 0.75))
        thr_action = float(thr_obj.get("action", 0.85))
    else:
        thr_intent = thr_action = float(thr_obj)
    intent_conf = float(pred.get("intent_confidence_calibrated", 0.0))
    action_conf = float(pred.get("action_confidence_calibrated", 0.0))
    return (
        intent_conf >= thr_intent
        and action_conf >= thr_action
        and bool(pred.get("action_required"))
        and pred.get("intent_type") in {"REQUEST", "COMMAND"}
    )


def _compute_metrics(predictions: List[Dict[str, Any]], gold_items: List[Dict[str, Any]],
                     mode: str, dataset_id: str, dataset_file: str,
                     merge_sha: str) -> Dict[str, Any]:
    """13지표 계산 (알고리즘 팀 권장 구조)."""
    total = len(predictions)
    # gold ↔ pred 매핑 by sample_id
    gold_by_id = {g["sample_id"]: g for g in gold_items}

    schema_valid_count = 0
    no_action_fp = 0
    no_action_gold = 0
    false_deadline = 0
    verifier_error_auto_apply = 0
    pred_auto_true = 0
    gold_auto_true = 0
    tp_auto = fp_auto = fn_auto = tn_auto = 0

    # extraction quality
    norm_action_tp = norm_action_fp = norm_action_fn = 0
    multi_action_split_ok = multi_action_split_total = 0
    deadline_tp = deadline_fp = deadline_fn = 0

    intent_correct = 0

    # calibration ECE (action / intent)
    intent_confs: List[Tuple[float, int]] = []
    action_confs: List[Tuple[float, int]] = []

    for p in predictions:
        sid = p["sample_id"]
        gold = gold_by_id.get(sid) or {}
        pred = p.get("pred", {}) or {}

        if pred.get("schema_valid"):
            schema_valid_count += 1

        # intent compare (5분류 그대로)
        gold_intent = gold.get("intent_type")
        pred_intent = pred.get("intent_type")
        if gold_intent and pred_intent and gold_intent == pred_intent:
            intent_correct += 1

        # NO_ACTION FP: gold != NO_ACTION 인데 pred = NO_ACTION
        if gold_intent == "NO_ACTION":
            no_action_gold += 1
        if pred_intent == "NO_ACTION" and gold_intent and gold_intent != "NO_ACTION":
            no_action_fp += 1

        # false deadline: pred 가 deadline_is_actionable=true 인데 gold 가 NONE/INQUIRY/URGENCY/CONDITION
        gold_dtype = gold.get("deadline_type")
        pred_dtype = pred.get("deadline_type")
        pred_dact  = pred.get("deadline_is_actionable", False)
        if pred_dact and gold_dtype in {"NONE", "INQUIRY", "URGENCY", "CONDITION"}:
            false_deadline += 1

        # deadline F1 (HARD/SOFT 매칭)
        gold_has = gold_dtype in {"HARD", "SOFT"}
        pred_has = pred_dtype in {"HARD", "SOFT"}
        if gold_has and pred_has and gold_dtype == pred_dtype:
            deadline_tp += 1
        elif (not gold_has) and pred_has:
            deadline_fp += 1
        elif gold_has and (not pred_has or gold_dtype != pred_dtype):
            deadline_fn += 1

        # auto_apply matrix
        gold_auto = bool(gold.get("auto_apply_allowed"))
        pred_auto = bool(pred.get("auto_apply_allowed"))
        if gold_auto:    gold_auto_true += 1
        if pred_auto:    pred_auto_true += 1
        if pred_auto and gold_auto:           tp_auto += 1
        elif pred_auto and not gold_auto:     fp_auto += 1
        elif (not pred_auto) and gold_auto:   fn_auto += 1
        else:                                  tn_auto += 1

        # verifier_error_auto_apply: auto_apply=true 인데 verifier errors > 0
        verr = p.get("verifier_error_count", 0)
        if pred_auto and verr > 0:
            verifier_error_auto_apply += 1

        # normalized_action F1 (gold actions count vs pred actions count)
        gold_actions = gold.get("gold", {}).get("actions") or gold.get("actions") or []
        pred_actions = pred.get("actions") or []
        g_n, p_n = len(gold_actions), len(pred_actions)
        if g_n > 0 and p_n > 0:
            matched = min(g_n, p_n)
            norm_action_tp += matched
            norm_action_fp += max(0, p_n - matched)
            norm_action_fn += max(0, g_n - matched)
        elif p_n > 0:
            norm_action_fp += p_n
        elif g_n > 0:
            norm_action_fn += g_n

        # multi action split
        if g_n >= 2:
            multi_action_split_total += 1
            if p_n == g_n:
                multi_action_split_ok += 1

        # ECE collection
        ic = pred.get("intent_confidence_calibrated") or pred.get("raw_intent_confidence") or 0.0
        ac = pred.get("action_confidence_calibrated") or pred.get("raw_action_confidence") or 0.0
        intent_confs.append((float(ic), 1 if gold_intent == pred_intent else 0))
        action_confs.append((float(ac), 1 if g_n == p_n and g_n > 0 else 0))

    def _ece(samples: List[Tuple[float, int]], bins: int = 10) -> float:
        if not samples:
            return 0.0
        buckets = [[] for _ in range(bins)]
        for conf, correct in samples:
            idx = min(bins - 1, max(0, int(conf * bins)))
            buckets[idx].append((conf, correct))
        n = len(samples)
        ece = 0.0
        for b in buckets:
            if not b:
                continue
            avg_conf = sum(c for c, _ in b) / len(b)
            avg_acc  = sum(k for _, k in b) / len(b)
            ece += abs(avg_conf - avg_acc) * len(b) / n
        return ece

    schema_rate = schema_valid_count / total if total else 0.0
    naf1 = (2 * norm_action_tp / (2 * norm_action_tp + norm_action_fp + norm_action_fn)
            if (2 * norm_action_tp + norm_action_fp + norm_action_fn) > 0 else 0.0)
    masa = (multi_action_split_ok / multi_action_split_total
            if multi_action_split_total > 0 else 0.0)
    df1 = (2 * deadline_tp / (2 * deadline_tp + deadline_fp + deadline_fn)
           if (2 * deadline_tp + deadline_fp + deadline_fn) > 0 else 0.0)
    fd_rate = false_deadline / total if total else 0.0
    na_fp_rate = no_action_fp / max(1, total - no_action_gold)

    auto_prec = tp_auto / max(1, tp_auto + fp_auto)
    auto_rec  = tp_auto / max(1, tp_auto + fn_auto)

    action_ece = _ece(action_confs)
    intent_ece = _ece(intent_confs)

    return {
        "mode":                              mode,
        "merge_sha":                         merge_sha,
        "dataset_id":                        dataset_id,
        "dataset_file":                      dataset_file,
        "dataset_size":                      total,
        "sample_count":                      total,
        "schema_valid_rate":                 round(schema_rate, 4),
        "normalized_action_f1":              round(naf1, 4),
        "multi_action_split_accuracy":       round(masa, 4),
        "deadline_f1":                       round(df1, 4),
        "false_deadline_rate":               round(fd_rate, 4),
        "no_action_fp_rate":                 round(na_fp_rate, 4),
        "verifier_error_auto_apply_count":   verifier_error_auto_apply,
        "auto_apply_precision":              round(auto_prec, 4),
        "auto_apply_recall":                 round(auto_rec, 4),
        "action_ece_after":                  round(action_ece, 4),
        "intent_ece_after":                  round(intent_ece, 4),
        "g22_strict_warning_count":          0,  # 외부 G22 결과 주입
        "g23_hard_violation_count":          0,  # 외부 G23 결과 주입
        "intent_accuracy_reference_only":    round(intent_correct / total, 4) if total else 0.0,
        "production_candidate_thresholds": {
            "verifier_error_auto_apply_count_max": 0,
            "false_deadline_rate_max":              0.02,
            "no_action_fp_rate_max":                0.03,
            "g22_strict_warning_count_max":         0,
            "g23_hard_violation_count_max":         0,
            "auto_apply_precision_min":             0.95,
            "auto_apply_recall_min":                0.70,
            "schema_valid_rate_min":                0.98,
            "normalized_action_f1_min":             0.90,
            "multi_action_split_accuracy_min":      0.85,
            "deadline_f1_min":                      0.90,
            "action_ece_after_max":                 0.15,
            "intent_ece_after_max":                 0.20,
        },
        "judgment_priority": {
            "tier_1_hard_safety": ["verifier_error_auto_apply_count", "false_deadline_rate",
                                    "no_action_fp_rate", "g22_strict_warning_count",
                                    "g23_hard_violation_count"],
            "tier_2_auto_apply": ["auto_apply_precision", "auto_apply_recall"],
            "tier_3_extraction_quality": ["normalized_action_f1", "multi_action_split_accuracy",
                                          "deadline_f1", "schema_valid_rate"],
            "tier_4_calibration": ["action_ece_after", "intent_ece_after"],
        },
        "reference": {
            "auto_apply_rate_reference_only": round(pred_auto_true / total, 4) if total else 0.0,
            "pred_auto_apply_true_count":     pred_auto_true,
            "gold_auto_apply_true_count":     gold_auto_true,
        },
        "verdict": "MEASURED_ONLY",
        "evaluated_at": _now_iso(),
    }


def run(mode: str, items: List[Dict[str, Any]], out_dir: Path,
        calibrator: Optional[Dict[str, Any]], merge_sha: str,
        dataset_id: str, dataset_file: str, limit: Optional[int] = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    log_lines: List[str] = []
    started = time.time()
    predictions: List[Dict[str, Any]] = []

    src = items if limit is None else items[:limit]
    log_lines.append(f"[{_now_iso()}] start mode={mode} n={len(src)}")

    for idx, it in enumerate(src):
        sid = it["sample_id"]
        text = it.get("text") or it.get("text_redacted") or ""

        if mode == "A":
            pred = _mode_a_predict(text)
        elif mode == "B":
            pred = _llm_predict(text, hints=None)
        elif mode in {"C", "D"}:
            hints = {
                "deadlines": extract_deadlines(text),
                "actions":   extract_actions_candidates(text),
                "materials": extract_materials(text),
            }
            pred = _llm_predict(text, hints=hints)
        else:
            raise ValueError(f"unknown mode {mode!r}")

        # Mode D: calibration → candidate 산출 → verifier (V8/V9 적용) → 최종 결정
        # Codex P1-2 정정 (옵션 B+C): candidate 기반 V8/V9 순서 정합
        verifier_err_count = 0
        verifier_errors: List[str] = []
        if mode == "D":
            _apply_calibration(pred, calibrator or {})
            auto_candidate = _mode_d_compute_auto_candidate(pred, calibrator or {})
            vres = apply_card1_hard_rules(
                sample_id=sid, text=text, pred=pred,
                schema_valid=pred.get("schema_valid", True),
                base_verifier_errors=pred.get("base_verifier_errors") or [],
                duplicate_strict_warning=False,
                auto_apply_candidate=auto_candidate,
            )
            verifier_err_count = vres.error_count
            verifier_errors    = vres.errors
            pred["auto_apply_candidate"] = auto_candidate
            pred["auto_apply_allowed"]   = (
                auto_candidate and vres.error_count == 0
            )

        predictions.append({
            "sample_id":               sid,
            "pred":                    pred,
            "verifier_error_count":    verifier_err_count,
            "verifier_errors":         verifier_errors,
        })

        if (idx + 1) % 50 == 0:
            log_lines.append(f"[{_now_iso()}] mode={mode} processed {idx+1}/{len(src)}")

    elapsed = round(time.time() - started, 3)
    log_lines.append(f"[{_now_iso()}] end mode={mode} elapsed_sec={elapsed}")

    # write predictions.jsonl
    pred_path = out_dir / "predictions.jsonl"
    pred_path.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n",
        encoding="utf-8",
    )

    # write metrics
    metrics = _compute_metrics(predictions, items, mode, dataset_id, dataset_file, merge_sha)
    metrics["elapsed_sec"] = elapsed
    (out_dir / "metrics_13.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # run_config
    (out_dir / "run_config.json").write_text(json.dumps({
        "mode":          mode,
        "merge_sha":     merge_sha,
        "dataset_id":    dataset_id,
        "dataset_file":  dataset_file,
        "n_input":       len(src),
        "limit":         limit,
        "temperature":   0,
        "grammar":       "json_schema",
        "started_at":    datetime.fromtimestamp(started, tz=timezone.utc).isoformat(),
        "ended_at":      _now_iso(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # run.log
    (out_dir / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["A", "B", "C", "D"])
    p.add_argument("--input", required=True)
    p.add_argument("--dataset-id", default="card1_evalset_v1_1_500")
    p.add_argument("--output", required=True)
    p.add_argument("--merge-sha", default="3b7ab991ff19f45c14aa62d65ed43f325a5e25a3")
    p.add_argument("--calibrator", default="butler_pc_core/card1_extraction/calibrator_config.json")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"input missing: {in_path}", file=sys.stderr)
        return 1
    out_dir = Path(args.output)

    calibrator: Optional[Dict[str, Any]] = None
    if args.mode == "D":
        cal_path = Path(args.calibrator)
        if cal_path.exists():
            calibrator = json.loads(cal_path.read_text(encoding="utf-8"))

    items = _load_dataset(in_path)
    try:
        run(args.mode, items, out_dir, calibrator, args.merge_sha,
            args.dataset_id, str(in_path), limit=args.limit)
    except Exception as e:
        traceback.print_exc()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
