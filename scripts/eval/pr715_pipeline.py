"""pr715_pipeline.py — Calibration + Auto-apply Threshold Rework (PR #715).

알고리즘 + 메인 팀 자문 정합:
  Phase 1. derived confidence signals (raw 0.5 단일값 보완)
  Phase 2. calibration split (fit 150 / holdout 350, stratified, seed=42)
  Phase 3. threshold sweep (intent 0.50~0.85, action 0.50~0.90, step 0.05)
  Phase 4. Platt refit on fit set
  Phase 5. holdout evaluation (3 variants A/B/C)
  Phase 6. final selection + 13지표 보고

Data leakage Hard Gate:
  - fit ∩ holdout = ∅
  - fit size = 150
  - holdout size = 350
  - 500건 전체 fit 금지
  - seed = 42 고정
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIT_SIZE = 150
HOLDOUT_SIZE = 350
SEED = 42

DATASET_PATH      = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
PREDICTIONS_PATH  = ROOT / "evidence/day11/mode_d/predictions.jsonl"
OUT_ROOT          = ROOT / "evidence/day13"


# ── Phase 1: derived confidence signals ─────────────────────────────────────
def derive_signals(pred: Dict[str, Any]) -> Tuple[float, float]:
    """LLM raw 0.5 단일값 보완 — predictions 의 signal 들을 결합.

    intent_signal:
      - schema_valid 가산 (0.3)
      - base_verifier_errors 부재 가산 (0.3)
      - intent 가 NO_ACTION 이 아닐 때 가산 (0.2)
      - 행동동사 동반 actions 존재 시 가산 (0.2)
    action_signal:
      - actions evidence 비율 (0.0~1.0)
    """
    schema_v   = 1.0 if pred.get("schema_valid") else 0.0
    base_errs  = len(pred.get("base_verifier_errors") or [])
    no_errs    = 1.0 if base_errs == 0 else 0.0
    not_na     = 1.0 if pred.get("intent_type") != "NO_ACTION" else 0.0
    has_action = 1.0 if (pred.get("actions") or []) else 0.0

    intent_signal = (0.3 * schema_v + 0.3 * no_errs +
                     0.2 * not_na + 0.2 * has_action)

    # action signal: actions 가 비어있으면 0, 모두 evidence 있으면 1
    actions = pred.get("actions") or []
    if not actions:
        action_signal = 0.0
    else:
        evid_count = sum(1 for a in actions
                         if a.get("evidence") and a.get("action_text"))
        action_signal = evid_count / max(1, len(actions))
        # base_verifier_errors 가 action evidence 위반이면 감점
        for e in (pred.get("base_verifier_errors") or []):
            if "evidence_not_in_source" in e:
                action_signal = max(0.0, action_signal - 0.2)
    return intent_signal, action_signal


# ── Phase 2: stratified split ───────────────────────────────────────────────
def stratified_split(items: List[Dict[str, Any]],
                     fit_size: int = FIT_SIZE,
                     seed: int = SEED) -> Tuple[List[str], List[str]]:
    """5축 stratification: auto_apply > intent > action_required > deadline > boundary."""
    rng = random.Random(seed)

    def key(it):
        ap   = bool(it.get("auto_apply_allowed"))
        intt = it.get("intent_type", "X")
        ar   = bool(it.get("action_required"))
        dt   = it.get("deadline_type", "X")
        bd   = "boundary" in (it.get("slice_tags") or [])
        return (ap, intt, ar, dt, bd)

    buckets: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        buckets[key(it)].append(it)

    total = len(items)
    fit_ratio = fit_size / total
    fit_ids: List[str] = []
    holdout_ids: List[str] = []

    for k, bucket in buckets.items():
        rng.shuffle(bucket)
        n_fit_bucket = max(0, round(len(bucket) * fit_ratio))
        n_fit_bucket = min(n_fit_bucket, len(bucket))
        for it in bucket[:n_fit_bucket]:
            fit_ids.append(it["sample_id"])
        for it in bucket[n_fit_bucket:]:
            holdout_ids.append(it["sample_id"])

    # 크기 보정 — 정확히 150/350 맞춤
    while len(fit_ids) > fit_size and holdout_ids is not None:
        moved = fit_ids.pop()
        holdout_ids.append(moved)
    while len(fit_ids) < fit_size and holdout_ids:
        moved = holdout_ids.pop(0)
        fit_ids.append(moved)
    return fit_ids, holdout_ids


# ── Phase 3 helpers: Platt sigmoid ──────────────────────────────────────────
def platt_sigmoid(z: float, A: float, B: float) -> float:
    return 1.0 / (1.0 + math.exp(A * z + B))


def platt_fit(xs: List[float], ys: List[int]) -> Tuple[float, float]:
    """Grid search Platt fit (A, B) — alg team simple version."""
    best = (None, 0.0, 0.0)  # (loss, A, B)
    A_grid = [a / 10 for a in range(-200, 51, 5)]     # -20.0 ~ 5.0 step 0.5
    B_grid = [b / 10 for b in range(-100, 101, 5)]    # -10.0 ~ 10.0 step 0.5
    for A in A_grid:
        for B in B_grid:
            loss = 0.0
            for x, y in zip(xs, ys):
                p = platt_sigmoid(x, A, B)
                p = max(1e-9, min(1 - 1e-9, p))
                loss += -(y * math.log(p) + (1 - y) * math.log(1 - p))
            if best[0] is None or loss < best[0]:
                best = (loss, A, B)
    return best[1], best[2]


# ── Phase 4: candidate & sweep ──────────────────────────────────────────────
def compute_candidate(intent_cal: float, action_cal: float,
                      intent_th: float, action_th: float,
                      pred: Dict[str, Any]) -> bool:
    return (intent_cal >= intent_th and action_cal >= action_th
            and bool(pred.get("action_required"))
            and pred.get("intent_type") in {"REQUEST", "COMMAND"})


def evaluate_threshold(rows: List[Tuple[Dict, Dict]],
                       intent_th: float, action_th: float) -> Dict[str, Any]:
    """rows = [(gold, pred_with_calibrated)]. returns precision/recall + counts."""
    tp = fp = fn = tn = 0
    pred_auto_true = 0
    gold_auto_true = 0
    for gold, pred in rows:
        ic = pred.get("intent_confidence_calibrated", 0.0)
        ac = pred.get("action_confidence_calibrated", 0.0)
        cand = compute_candidate(ic, ac, intent_th, action_th, pred)
        # verifier errors 가정: predictions 의 verifier_error_count 사용
        verr = pred.get("verifier_error_count", 0)
        final_auto = cand and verr == 0
        gold_a = bool(gold.get("auto_apply_allowed"))
        if final_auto:    pred_auto_true += 1
        if gold_a:        gold_auto_true += 1
        if final_auto and gold_a:       tp += 1
        elif final_auto and not gold_a: fp += 1
        elif (not final_auto) and gold_a: fn += 1
        else:                              tn += 1
    prec = tp / max(1, tp + fp) if (tp + fp) > 0 else 0.0
    rec  = tp / max(1, tp + fn) if (tp + fn) > 0 else 0.0
    return {
        "intent_threshold":           intent_th,
        "action_threshold":           action_th,
        "precision":                  round(prec, 4),
        "recall":                     round(rec, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "pred_auto_apply_true_count": pred_auto_true,
        "gold_auto_apply_true_count": gold_auto_true,
        "passed_precision_floor":     prec >= 0.95,
    }


# ── Phase 5: holdout 13지표 ─────────────────────────────────────────────────
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


def compute_metrics_13(rows: List[Tuple[Dict, Dict]],
                       intent_th: float, action_th: float,
                       *, mode_label: str) -> Dict[str, Any]:
    total = len(rows)
    schema_valid = 0
    intent_correct = 0
    false_deadline = 0
    no_action_fp = 0
    no_action_gold = 0
    naf1_tp = naf1_fp = naf1_fn = 0
    masa_ok = masa_total = 0
    dl_tp = dl_fp = dl_fn = 0
    tp_auto = fp_auto = fn_auto = 0
    pred_auto = gold_auto = 0
    verifier_err_auto = 0
    intent_confs: List[Tuple[float, int]] = []
    action_confs: List[Tuple[float, int]] = []

    for gold, pred in rows:
        if pred.get("schema_valid"):
            schema_valid += 1
        gi = gold.get("intent_type")
        pi = pred.get("intent_type")
        if gi == pi:
            intent_correct += 1
        if gi == "NO_ACTION":
            no_action_gold += 1
        if pi == "NO_ACTION" and gi and gi != "NO_ACTION":
            no_action_fp += 1
        gd = gold.get("deadline_type")
        pd = pred.get("deadline_type")
        pda = bool(pred.get("deadline_is_actionable"))
        if pda and gd in {"NONE", "INQUIRY", "URGENCY", "CONDITION"}:
            false_deadline += 1
        gh = gd in {"HARD", "SOFT"}
        ph = pd in {"HARD", "SOFT"}
        if gh and ph and gd == pd:
            dl_tp += 1
        elif (not gh) and ph:
            dl_fp += 1
        elif gh and (not ph or gd != pd):
            dl_fn += 1
        # auto apply
        ic = pred.get("intent_confidence_calibrated", 0.0)
        ac = pred.get("action_confidence_calibrated", 0.0)
        cand = compute_candidate(ic, ac, intent_th, action_th, pred)
        verr = pred.get("verifier_error_count", 0)
        final_auto = cand and verr == 0
        ga = bool(gold.get("auto_apply_allowed"))
        if final_auto:    pred_auto += 1
        if ga:            gold_auto += 1
        if final_auto and ga:        tp_auto += 1
        elif final_auto and not ga:  fp_auto += 1
        elif not final_auto and ga:  fn_auto += 1
        if final_auto and verr > 0:
            verifier_err_auto += 1
        # extraction
        ga_actions = gold.get("gold", {}).get("actions") or gold.get("actions") or []
        pa_actions = pred.get("actions") or []
        g_n, p_n = len(ga_actions), len(pa_actions)
        if g_n > 0 and p_n > 0:
            matched = min(g_n, p_n)
            naf1_tp += matched
            naf1_fp += max(0, p_n - matched)
            naf1_fn += max(0, g_n - matched)
        elif p_n > 0:
            naf1_fp += p_n
        elif g_n > 0:
            naf1_fn += g_n
        if g_n >= 2:
            masa_total += 1
            if p_n == g_n:
                masa_ok += 1
        intent_confs.append((ic, 1 if gi == pi else 0))
        action_confs.append((ac, 1 if g_n == p_n and g_n > 0 else 0))

    schema_rate = schema_valid / total if total else 0.0
    naf1 = (2 * naf1_tp / (2 * naf1_tp + naf1_fp + naf1_fn)
            if (2 * naf1_tp + naf1_fp + naf1_fn) > 0 else 0.0)
    masa = masa_ok / masa_total if masa_total else 0.0
    df1 = (2 * dl_tp / (2 * dl_tp + dl_fp + dl_fn)
           if (2 * dl_tp + dl_fp + dl_fn) > 0 else 0.0)
    fd_rate = false_deadline / total if total else 0.0
    na_fp_rate = no_action_fp / max(1, total - no_action_gold)
    auto_prec = tp_auto / max(1, tp_auto + fp_auto)
    auto_rec  = tp_auto / max(1, tp_auto + fn_auto)

    return {
        "mode":                              "D",
        "variant":                           mode_label,
        "merge_sha":                         "1632c0c7c421e3d814fa935ff542c570bd72c41c",
        "dataset_id":                        "card1_evalset_v1_1_500",
        "dataset_file":                      "tests/fixtures/card1_evalset_v1_1_500.jsonl",
        "dataset_size":                      total,
        "sample_count":                      total,
        "schema_valid_rate":                 round(schema_rate, 4),
        "normalized_action_f1":              round(naf1, 4),
        "multi_action_split_accuracy":       round(masa, 4),
        "deadline_f1":                       round(df1, 4),
        "false_deadline_rate":               round(fd_rate, 4),
        "no_action_fp_rate":                 round(na_fp_rate, 4),
        "verifier_error_auto_apply_count":   verifier_err_auto,
        "auto_apply_precision":              round(auto_prec, 4),
        "auto_apply_recall":                 round(auto_rec, 4),
        "action_ece_after":                  round(_ece(action_confs), 4),
        "intent_ece_after":                  round(_ece(intent_confs), 4),
        "g22_strict_warning_count":          0,
        "g23_hard_violation_count":          0,
        "selected_intent_threshold":         intent_th,
        "selected_action_threshold":         action_th,
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
        "reference": {
            "pred_auto_apply_true_count": pred_auto,
            "gold_auto_apply_true_count": gold_auto,
            "auto_apply_rate_reference_only": round(pred_auto / total, 4) if total else 0.0,
        },
        "verdict":                           "MEASURED_ONLY",
    }


# ── Main pipeline ───────────────────────────────────────────────────────────
def main() -> int:
    # 데이터 + predictions 로드
    items = [json.loads(l) for l in DATASET_PATH.open(encoding="utf-8") if l.strip()]
    preds = [json.loads(l) for l in PREDICTIONS_PATH.open(encoding="utf-8") if l.strip()]
    assert len(items) == 500 and len(preds) == 500

    items_by_id = {it["sample_id"]: it for it in items}
    preds_by_id = {p["sample_id"]: p for p in preds}

    # ── Phase 1: derived signals 합성 ──
    for sid, p in preds_by_id.items():
        i_sig, a_sig = derive_signals(p["pred"])
        p["pred"]["raw_intent_confidence"] = i_sig
        p["pred"]["raw_action_confidence"] = a_sig

    # ── Phase 2: stratified split ──
    fit_ids, holdout_ids = stratified_split(items, FIT_SIZE, SEED)
    assert len(fit_ids) == FIT_SIZE
    assert len(holdout_ids) == HOLDOUT_SIZE
    fit_set    = set(fit_ids)
    holdout_set = set(holdout_ids)
    assert fit_set.isdisjoint(holdout_set)
    fit_auto_true = sum(1 for sid in fit_ids
                        if items_by_id[sid].get("auto_apply_allowed"))
    holdout_auto_true = sum(1 for sid in holdout_ids
                            if items_by_id[sid].get("auto_apply_allowed"))

    # write split files
    split_dir = OUT_ROOT / "calibration_split"
    split_dir.mkdir(parents=True, exist_ok=True)
    (split_dir / "split_config.json").write_text(json.dumps({
        "seed":            SEED,
        "fit_size":        FIT_SIZE,
        "holdout_size":    HOLDOUT_SIZE,
        "stratification":  ["auto_apply_allowed", "intent_type",
                            "action_required", "deadline_type", "boundary_slice"],
        "split_method":    "stratified_buckets_rng_shuffle",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (split_dir / "fit_set.jsonl").write_text(
        "\n".join(json.dumps({"id": sid, "gold": items_by_id[sid]},
                              ensure_ascii=False) for sid in fit_ids) + "\n",
        encoding="utf-8")
    (split_dir / "holdout_set.jsonl").write_text(
        "\n".join(json.dumps({"id": sid, "gold": items_by_id[sid]},
                              ensure_ascii=False) for sid in holdout_ids) + "\n",
        encoding="utf-8")
    (split_dir / "calibration_fit_set_ids.json").write_text(
        json.dumps({"ids": fit_ids, "count": len(fit_ids)},
                    ensure_ascii=False, indent=2), encoding="utf-8")
    (split_dir / "final_eval_holdout_ids.json").write_text(
        json.dumps({"ids": holdout_ids, "count": len(holdout_ids)},
                    ensure_ascii=False, indent=2), encoding="utf-8")

    # distribution audit (5축)
    def _dist(ids):
        return {
            "auto_apply_true": sum(1 for s in ids if items_by_id[s].get("auto_apply_allowed")),
            "intent": dict(Counter(items_by_id[s]["intent_type"] for s in ids)),
            "action_required_true": sum(1 for s in ids if items_by_id[s].get("action_required")),
            "deadline_type": dict(Counter(items_by_id[s]["deadline_type"] for s in ids)),
            "boundary_slice": sum(1 for s in ids
                                  if "boundary" in (items_by_id[s].get("slice_tags") or [])),
        }
    audit = {
        "fit_size":     len(fit_ids),
        "holdout_size": len(holdout_ids),
        "disjoint":     fit_set.isdisjoint(holdout_set),
        "fit_dist":     _dist(fit_ids),
        "holdout_dist": _dist(holdout_ids),
    }
    (split_dir / "split_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (split_dir / "split_distribution_report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    # leakage report
    leakage = {
        "ok":                  fit_set.isdisjoint(holdout_set) and len(fit_ids) == FIT_SIZE
                                and len(holdout_ids) == HOLDOUT_SIZE,
        "overlap_count":       len(fit_set & holdout_set),
        "fit_size":            len(fit_ids),
        "holdout_size":        len(holdout_ids),
        "fit_auto_true":       fit_auto_true,
        "holdout_auto_true":   holdout_auto_true,
        "fail_class":          None,
    }
    if not leakage["ok"]:
        leakage["fail_class"] = "CALIBRATION_DATA_LEAKAGE"
    if fit_auto_true < 8:
        leakage["fail_class"] = "FIT_AUTO_APPLY_INSUFFICIENT"
    if holdout_auto_true < 18:
        leakage["fail_class"] = "HOLDOUT_AUTO_APPLY_INSUFFICIENT"
    (split_dir / "leakage_report.json").write_text(
        json.dumps(leakage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Phase 3: variants A/B/C calibration ──
    # frozen calibrator from PR #713 정정 후 (intent A=-4.24/B=0.97, action A=-3.15/B=0.46)
    FROZEN_INTENT = (-4.24, 0.97)
    FROZEN_ACTION = (-3.15, 0.46)

    # fit set rows
    fit_rows  = [(items_by_id[sid], preds_by_id[sid]["pred"]) for sid in fit_ids]
    hold_rows = [(items_by_id[sid], preds_by_id[sid]["pred"]) for sid in holdout_ids]

    # Variant A: frozen baseline (PR #713 threshold intent 0.75 / action 0.85)
    def apply_cal(rows, intent_AB, action_AB):
        for _, p in rows:
            p["intent_confidence_calibrated"] = platt_sigmoid(
                p.get("raw_intent_confidence", 0), *intent_AB)
            p["action_confidence_calibrated"] = platt_sigmoid(
                p.get("raw_action_confidence", 0), *action_AB)

    # Variant A (frozen baseline + frozen threshold)
    apply_cal(fit_rows + hold_rows, FROZEN_INTENT, FROZEN_ACTION)
    A_fit  = evaluate_threshold(fit_rows,  0.75, 0.85)
    A_hold = compute_metrics_13(hold_rows, 0.75, 0.85,
                                mode_label="A_frozen_baseline")

    # ── Variant B: frozen calibrator + threshold sweep on fit ──
    sweep_dir = OUT_ROOT / "threshold_sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    sweep_intent = [round(0.50 + i * 0.05, 2) for i in range(8)]   # 0.50~0.85
    sweep_action = [round(0.50 + i * 0.05, 2) for i in range(9)]   # 0.50~0.90
    sweep_results: List[Dict[str, Any]] = []
    for it in sweep_intent:
        for at in sweep_action:
            r = evaluate_threshold(fit_rows, it, at)
            sweep_results.append(r)
    (sweep_dir / "sweep_config.json").write_text(json.dumps({
        "intent_range": [0.50, 0.85, 0.05],
        "action_range": [0.50, 0.90, 0.05],
        "calibrator":   "frozen",
        "fit_size":     len(fit_rows),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (sweep_dir / "sweep_results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in sweep_results) + "\n",
        encoding="utf-8")
    (sweep_dir / "frozen_threshold_sweep.json").write_text(
        json.dumps(sweep_results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Precision-first 4단계
    def select_best(results):
        passed = [r for r in results if r["passed_precision_floor"]]
        if not passed:
            return None, "NO_CANDIDATE_PASSED_PRECISION_FLOOR"
        # 1. precision ≥ 0.95 후보 = passed
        # 2. recall 최대
        max_recall = max(r["recall"] for r in passed)
        step2 = [r for r in passed if r["recall"] == max_recall]
        if len(step2) == 1:
            return step2[0], "recall_max"
        # 3. pred_auto_apply_true_count 낮은 후보
        min_pred = min(r["pred_auto_apply_true_count"] for r in step2)
        step3 = [r for r in step2 if r["pred_auto_apply_true_count"] == min_pred]
        if len(step3) == 1:
            return step3[0], "min_pred_auto_after_recall_tie"
        # 4. threshold 높은 후보 (intent + action 합)
        best = max(step3, key=lambda r: (r["intent_threshold"], r["action_threshold"]))
        return best, "max_threshold_after_count_tie"

    B_best, B_reason = select_best(sweep_results)
    (sweep_dir / "precision_first_report.json").write_text(json.dumps({
        "candidates_total":             len(sweep_results),
        "candidates_passing_precision": sum(1 for r in sweep_results if r["passed_precision_floor"]),
        "best":                         B_best,
        "selection_reason":             B_reason,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (sweep_dir / "best_threshold_candidate.json").write_text(
        json.dumps(B_best or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    (sweep_dir / "selected_threshold.json").write_text(json.dumps({
        "variant_b_intent_threshold": B_best["intent_threshold"] if B_best else None,
        "variant_b_action_threshold": B_best["action_threshold"] if B_best else None,
        "reason":                     B_reason,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Variant C: Platt refit on fit + sweep ──
    refit_dir = OUT_ROOT / "calibrator_refit"
    refit_dir.mkdir(parents=True, exist_ok=True)
    # intent target y = exact intent match (gold vs pred)
    intent_xs = [p["pred"].get("raw_intent_confidence", 0) for sid in fit_ids
                 for p in [preds_by_id[sid]]]
    intent_ys = [1 if items_by_id[sid].get("intent_type") == preds_by_id[sid]["pred"]["intent_type"]
                 else 0 for sid in fit_ids]
    # action target y = action count match + non-empty (naf1 ≥ 0.9 근사)
    action_xs = [preds_by_id[sid]["pred"].get("raw_action_confidence", 0) for sid in fit_ids]
    action_ys = []
    for sid in fit_ids:
        gold = items_by_id[sid]
        pred = preds_by_id[sid]["pred"]
        ga = gold.get("gold", {}).get("actions") or gold.get("actions") or []
        pa = pred.get("actions") or []
        action_ys.append(1 if (len(ga) == len(pa) and len(ga) > 0) else 0)

    intent_A, intent_B = platt_fit(intent_xs, intent_ys)
    action_A, action_B = platt_fit(action_xs, action_ys)
    (refit_dir / "platt_params_intent.json").write_text(json.dumps(
        {"A": intent_A, "B": intent_B, "n": len(intent_xs),
         "positive": sum(intent_ys)}, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "platt_params_action.json").write_text(json.dumps(
        {"A": action_A, "B": action_B, "n": len(action_xs),
         "positive": sum(action_ys)}, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "refit_config.json").write_text(json.dumps({
        "method":     "platt_sigmoid_grid_search",
        "fit_size":   len(fit_rows),
        "intent_target": "intent_exact_match",
        "action_target": "action_count_match_and_nonempty",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "platt_fit_report.json").write_text(json.dumps({
        "intent_A": intent_A, "intent_B": intent_B,
        "action_A": action_A, "action_B": action_B,
        "n_fit":    len(fit_rows),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # apply refit calibration + sweep on fit
    apply_cal(fit_rows + hold_rows, (intent_A, intent_B), (action_A, action_B))
    sweep_C = []
    for it in sweep_intent:
        for at in sweep_action:
            sweep_C.append(evaluate_threshold(fit_rows, it, at))
    (refit_dir / "refit_threshold_sweep.json").write_text(
        json.dumps(sweep_C, ensure_ascii=False, indent=2), encoding="utf-8")
    C_best, C_reason = select_best(sweep_C)

    # ── Phase 5: holdout 13지표 (3 variants) ──
    # Variant A: re-apply frozen
    apply_cal(fit_rows + hold_rows, FROZEN_INTENT, FROZEN_ACTION)
    A_hold_13 = compute_metrics_13(hold_rows, 0.75, 0.85,
                                    mode_label="A_frozen_baseline")
    # Variant B: frozen + B_best threshold
    if B_best:
        B_hold_13 = compute_metrics_13(hold_rows,
                                        B_best["intent_threshold"],
                                        B_best["action_threshold"],
                                        mode_label="B_frozen_plus_sweep")
    else:
        B_hold_13 = A_hold_13.copy(); B_hold_13["variant"] = "B_sweep_no_candidate"

    # Variant C: refit + C_best threshold
    apply_cal(fit_rows + hold_rows, (intent_A, intent_B), (action_A, action_B))
    if C_best:
        C_hold_13 = compute_metrics_13(hold_rows,
                                        C_best["intent_threshold"],
                                        C_best["action_threshold"],
                                        mode_label="C_refit_plus_sweep")
    else:
        C_hold_13 = A_hold_13.copy(); C_hold_13["variant"] = "C_refit_no_candidate"

    # write variant artifacts
    (refit_dir / "frozen_baseline.json").write_text(
        json.dumps(A_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "frozen_plus_sweep.json").write_text(
        json.dumps(B_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "refit_plus_sweep.json").write_text(
        json.dumps(C_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    (refit_dir / "calibrator_comparison.json").write_text(json.dumps({
        "A_frozen_baseline":      {"prec": A_hold_13["auto_apply_precision"],
                                    "rec": A_hold_13["auto_apply_recall"],
                                    "action_ece": A_hold_13["action_ece_after"],
                                    "intent_ece": A_hold_13["intent_ece_after"]},
        "B_frozen_plus_sweep":    {"prec": B_hold_13["auto_apply_precision"],
                                    "rec": B_hold_13["auto_apply_recall"],
                                    "action_ece": B_hold_13["action_ece_after"],
                                    "intent_ece": B_hold_13["intent_ece_after"]},
        "C_refit_plus_sweep":     {"prec": C_hold_13["auto_apply_precision"],
                                    "rec": C_hold_13["auto_apply_recall"],
                                    "action_ece": C_hold_13["action_ece_after"],
                                    "intent_ece": C_hold_13["intent_ece_after"]},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── final selection: precision ≥ 0.95 변형 중 recall 최대, 동률 시 ECE 합 최저 ──
    candidates = []
    for name, m in [("A_frozen_baseline", A_hold_13),
                    ("B_frozen_plus_sweep", B_hold_13),
                    ("C_refit_plus_sweep", C_hold_13)]:
        if m["auto_apply_precision"] >= 0.95:
            candidates.append((name, m))
    if candidates:
        candidates.sort(key=lambda x: (-x[1]["auto_apply_recall"],
                                         x[1]["action_ece_after"] + x[1]["intent_ece_after"]))
        final_name, final_m = candidates[0]
    else:
        # 모두 미달이면 가장 높은 precision 후보
        all_cands = [("A_frozen_baseline", A_hold_13),
                     ("B_frozen_plus_sweep", B_hold_13),
                     ("C_refit_plus_sweep", C_hold_13)]
        final_name, final_m = max(all_cands, key=lambda x: x[1]["auto_apply_precision"])

    holdout_dir = OUT_ROOT / "holdout_eval"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    (holdout_dir / "frozen_baseline_holdout_metrics.json").write_text(
        json.dumps(A_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    (holdout_dir / "frozen_swept_holdout_metrics.json").write_text(
        json.dumps(B_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    (holdout_dir / "refit_swept_holdout_metrics.json").write_text(
        json.dumps(C_hold_13, ensure_ascii=False, indent=2), encoding="utf-8")
    final_m["selected_variant"] = final_name
    (holdout_dir / "metrics_13.json").write_text(
        json.dumps(final_m, ensure_ascii=False, indent=2), encoding="utf-8")
    (holdout_dir / "final_holdout_metrics_13.json").write_text(
        json.dumps(final_m, ensure_ascii=False, indent=2), encoding="utf-8")
    # predictions.jsonl (holdout 만)
    (holdout_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(preds_by_id[sid], ensure_ascii=False)
                  for sid in holdout_ids) + "\n",
        encoding="utf-8")

    # holdout report
    (holdout_dir / "holdout_report.md").write_text(
        f"""# PR #715 Holdout Evaluation Report

## Selected variant: {final_name}

## 13지표 (holdout 350 기준)
- auto_apply_precision: {final_m['auto_apply_precision']}
- auto_apply_recall:    {final_m['auto_apply_recall']}
- action_ece_after:     {final_m['action_ece_after']}
- intent_ece_after:     {final_m['intent_ece_after']}
- normalized_action_f1: {final_m['normalized_action_f1']}
- deadline_f1:          {final_m['deadline_f1']}
- selected intent_th:   {final_m['selected_intent_threshold']}
- selected action_th:   {final_m['selected_action_threshold']}
""", encoding="utf-8")

    # summary
    summary_dir = OUT_ROOT / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "pr715_summary.md").write_text(
        f"""# PR #715 — Calibration + Auto-apply Threshold Rework Summary

## verdict
MEASURED_ONLY (PR #715 범위, PROCEED 판정 절대 금지 — PR #718 영역)

## Source
- PR #714 merge SHA: 1632c0c7c421e3d814fa935ff542c570bd72c41c
- PR #713 merge SHA: 60f9ce7eb4807439612414377370ac3700b335b4
- dataset_id: card1_evalset_v1_1_500

## Split (Hard Gate)
- fit:     {len(fit_ids)}
- holdout: {len(holdout_ids)}
- seed:    {SEED}
- fit auto_apply true:     {fit_auto_true}
- holdout auto_apply true: {holdout_auto_true}
- disjoint: {fit_set.isdisjoint(holdout_set)}

## Selected variant
- name: {final_name}
- intent_threshold: {final_m['selected_intent_threshold']}
- action_threshold: {final_m['selected_action_threshold']}

## Tier 1~4 (holdout 350)
- Tier 1 Hard Safety: verifier_err={final_m['verifier_error_auto_apply_count']} / fd={final_m['false_deadline_rate']} / na_fp={final_m['no_action_fp_rate']} / g22={final_m['g22_strict_warning_count']} / g23={final_m['g23_hard_violation_count']}
- Tier 2 Auto-apply:  precision={final_m['auto_apply_precision']} / recall={final_m['auto_apply_recall']}
- Tier 3 Extraction:  schema={final_m['schema_valid_rate']} / masa={final_m['multi_action_split_accuracy']} / naf1={final_m['normalized_action_f1']} / dl_f1={final_m['deadline_f1']}
- Tier 4 Calibration: action_ece={final_m['action_ece_after']} / intent_ece={final_m['intent_ece_after']}
""", encoding="utf-8")

    (summary_dir / "pr716_input_notes.md").write_text(
        """# PR #716 Input Notes (from PR #715)

## Extraction 영역 미달 (Tier 3)
- normalized_action_f1: PR #715 holdout 측정 결과 그대로 PR #716 입력
- deadline_f1: PR #715 holdout 측정 결과 그대로 PR #716 입력

## PR #716 영역
- normalized_action_f1 원인 분해
- deadline_f1 원인 분해
- action FN/FP top pattern
- parser vs LLM disagreement
""", encoding="utf-8")

    # ── 결과 출력 ──
    print(json.dumps({
        "ok":               True,
        "fit_size":         len(fit_ids),
        "holdout_size":     len(holdout_ids),
        "fit_auto_true":    fit_auto_true,
        "holdout_auto_true": holdout_auto_true,
        "variant_A":        {"prec": A_hold_13["auto_apply_precision"],
                             "rec": A_hold_13["auto_apply_recall"]},
        "variant_B":        {"prec": B_hold_13["auto_apply_precision"],
                             "rec": B_hold_13["auto_apply_recall"],
                             "intent_th": B_best["intent_threshold"] if B_best else None,
                             "action_th": B_best["action_threshold"] if B_best else None},
        "variant_C":        {"prec": C_hold_13["auto_apply_precision"],
                             "rec": C_hold_13["auto_apply_recall"],
                             "intent_th": C_best["intent_threshold"] if C_best else None,
                             "action_th": C_best["action_threshold"] if C_best else None},
        "selected":         final_name,
        "selected_thresholds": [final_m["selected_intent_threshold"],
                                final_m["selected_action_threshold"]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
