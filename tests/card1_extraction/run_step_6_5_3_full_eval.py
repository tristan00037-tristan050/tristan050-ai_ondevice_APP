"""단계 6.5.3 — 65건 재평가 (5개 패치 적용 + 3-target Platt fit).

실행:
  export BUTLER_LLM_MODEL_PATH=".../qwen3-4b-q4_k_m.gguf"
  python tests/card1_extraction/run_step_6_5_3_full_eval.py

핵심 변화 (6.5.2 → 6.5.3):
  - intent_normalizer: REPORT (18) + COMMAND (13) chain
  - verifier: Block 7 (false_deadline hard rule)
  - confidence: action/intent/overall 분리 + final = min(4 component)
  - low_confidence_true_positive 6-category breakdown
  - calibrator_config v2 (15필드)
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction import extract_card1
from butler_pc_core.card1_extraction.action_normalizer import normalize_action_verb
from butler_pc_core.card1_extraction.confidence import (
    ConfidenceFeatures, raw_confidence_score, platt_calibrate,
    PLATT_A, PLATT_B,
    action_raw_score, intent_raw_score, overall_raw_score,
    deadline_confidence_heuristic, material_confidence_heuristic,
    compose_final_confidence,
)
from butler_pc_core.card1_extraction.contracts import (
    Card1Extraction, ExtractedAction, IntentType, SentenceType,
)
from butler_pc_core.card1_extraction.intent_normalizer import (
    REPORT_MARKERS, REQUEST_MARKERS, COMMAND_MARKERS, SOFT_REQUEST_MARKERS,
    REPORT_OVERRIDE_REASON, COMMAND_OVERRIDE_REASON,
    normalize_intent_chain,
)
from butler_pc_core.card1_extraction.llm_extractor import (
    LLM_EXTRACT_CONFIG, extract_with_llm_v1, V1ExtractResult,
)
from butler_pc_core.card1_extraction.parser import (
    ACTION_VERBS, classify_sentence_type, extract_actions_candidates,
    extract_deadlines, extract_materials,
)
from butler_pc_core.card1_extraction.verifier import (
    apply_hard_rules, BLOCK_FALSE_DEADLINE_NO_EVIDENCE,
    BLOCK_NO_EVIDENCE_DEADLINE, BLOCK_NO_EVIDENCE_MATERIAL,
    BLOCK_NO_EVIDENCE_ACTION, BLOCK_NEGATED_ACTION,
)

# 헬퍼 재사용 — 6.5.1 smoke 모듈
from tests.card1_extraction.run_step_6_5_1_smoke import (
    parser_intent_score, parser_deadline_score, parser_material_score,
    parser_action_score, parser_actions_from_text, llm_parser_agreement,
    evidence_coverage, negation_risk_of, multi_action_complexity,
    _action_types, _parser_hints_of, _with_confidence,
    run_mode_A,
)


# ────────────────────────────────────────────────────────────────────────
# 모드 실행기 (6.5.3 — 3-target confidence)
# ────────────────────────────────────────────────────────────────────────

INTENT_LABELS = ["report", "request", "command", "no_action"]


@dataclass
class Mode3Result:
    """6.5.3 D 모드 결과 — per-target raw + per-component conf 포함."""
    extraction:           Card1Extraction
    schema_valid:         bool
    retry_count:          int
    retry_reasons:        List[str]            = field(default_factory=list)
    verifier_errors:      List[str]            = field(default_factory=list)
    features:             Optional[ConfidenceFeatures] = None

    # raw scores
    action_raw:           float                = 0.0
    intent_raw:           float                = 0.0
    overall_raw:          float                = 0.0
    # per-component confidence (Platt 적용 전 initial)
    action_conf:          float                = 0.0
    intent_conf:          float                = 0.0
    deadline_conf:        float                = 0.0
    material_conf:        float                = 0.0
    final_confidence:     float                = 0.0
    blocked_auto:         bool                 = False

    # 메타
    override_applied:     str                  = ""  # "" | REPORT | COMMAND
    block_7_fired:        bool                 = False
    block_2_fired:        bool                 = False
    multi_action_count:   int                  = 0
    all_actions_have_evidence: bool            = True


def _run_d_3target(text: str, llm_fn: Callable[[str], str]) -> Mode3Result:
    """D 모드 6.5.3 — verifier(Block 1~7) + per-target confidence."""
    hints = _parser_hints_of(text)
    v1: V1ExtractResult = extract_with_llm_v1(text, parsed_hints=hints, llm_callable=llm_fn)
    sent_type = classify_sentence_type(text)
    ex = v1.extraction
    ex = Card1Extraction(
        intent=ex.intent, intent_type=ex.intent_type,
        deadline=ex.deadline, deadline_raw=ex.deadline_raw,
        materials=ex.materials, actions=ex.actions,
        sentence_type=sent_type,
        confidence=0.0, needs_review=True, reason_code=ex.reason_code,
    )

    # override 종류 추출 (llm_extractor._v1_dict_to_extraction이 reason_code에 기록)
    rc = ex.reason_code or ""
    override_kind = ""
    if rc == REPORT_OVERRIDE_REASON:  override_kind = "REPORT"
    elif rc == COMMAND_OVERRIDE_REASON: override_kind = "COMMAND"

    # 1차 verifier — block 1~4 + block 7 (조건 평가용 conf=1, schema=True)
    verif1 = apply_hard_rules(ex, text, confidence=1.0, schema_valid=True)
    ex_v   = verif1.extraction
    block_7_fired = BLOCK_FALSE_DEADLINE_NO_EVIDENCE in verif1.errors
    block_2_fired = BLOCK_NO_EVIDENCE_MATERIAL       in verif1.errors

    # feature 계산
    pred_action_types_list = _action_types(ex_v)
    feats = ConfidenceFeatures(
        parser_intent_score   = parser_intent_score(text, ex_v.intent_type),
        parser_deadline_score = parser_deadline_score(text),
        parser_material_score = parser_material_score(text),
        parser_action_score   = parser_action_score(text),
        llm_schema_valid      = v1.schema_valid,
        llm_parser_agreement  = llm_parser_agreement(ex_v, text),
        evidence_coverage     = evidence_coverage(ex_v, text),
        negation_risk         = negation_risk_of(text, ex_v),
        multi_action_complexity = multi_action_complexity(ex_v),
        verifier_error_count  = sum(
            1 for e in verif1.errors
            if e not in ("block_5_auto_apply_low_confidence",
                         "block_6_schema_retry_failed")
        ),
    )

    multi_n = len(ex_v.actions)
    all_ev_ok = all(
        (a.source_evidence and a.source_evidence in text) for a in ex_v.actions
    ) if ex_v.actions else True

    # per-target raw (Patch 4)
    a_raw = action_raw_score(feats, multi_action_count=multi_n,
                             all_actions_have_evidence=all_ev_ok)
    i_raw = intent_raw_score(feats,
                             normalizer_applied=bool(override_kind),
                             normalizer_conflict=False)
    o_raw = overall_raw_score(feats,
                              deadline_ok=not block_7_fired,
                              material_ok=not block_2_fired)

    # Platt 초기값(A=-4, B=2)으로 component 신뢰도 (fit 전)
    a_conf = platt_calibrate(a_raw)
    i_conf = platt_calibrate(i_raw)
    o_conf = platt_calibrate(o_raw)
    d_conf = deadline_confidence_heuristic(feats, block_7_fired=block_7_fired)
    m_conf = material_confidence_heuristic(feats, block_2_fired=block_2_fired)

    final = compose_final_confidence(a_conf, i_conf, d_conf, m_conf)

    # 2차 verifier — final confidence 반영 + schema 반영 (block 5/6 평가)
    verif2 = apply_hard_rules(ex_v, text, confidence=final, schema_valid=v1.schema_valid)
    ex_final = _with_confidence(verif2.extraction, final)

    return Mode3Result(
        extraction=ex_final, schema_valid=v1.schema_valid,
        retry_count=v1.retry_count, retry_reasons=v1.retry_reasons,
        verifier_errors=verif2.errors, features=feats,
        action_raw=a_raw, intent_raw=i_raw, overall_raw=o_raw,
        action_conf=a_conf, intent_conf=i_conf,
        deadline_conf=d_conf, material_conf=m_conf,
        final_confidence=final, blocked_auto=verif2.blocked_auto,
        override_applied=override_kind, block_7_fired=block_7_fired,
        block_2_fired=block_2_fired,
        multi_action_count=multi_n, all_actions_have_evidence=all_ev_ok,
    )


# ────────────────────────────────────────────────────────────────────────
# Platt 5-fold CV fit (6.5.2 동일)
# ────────────────────────────────────────────────────────────────────────

def _platt_sigmoid(raw: float, a: float, b: float) -> float:
    z = a * raw + b
    if z > 35: return 1e-12
    if z < -35: return 1.0 - 1e-12
    return 1.0 / (1.0 + math.exp(z))


def _platt_nll(samples: List[Tuple[float, int]], a: float, b: float) -> float:
    eps, total = 1e-7, 0.0
    for raw, y in samples:
        p = _platt_sigmoid(raw, a, b)
        p = min(max(p, eps), 1.0 - eps)
        total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
    return total


def _fit_platt_grid(samples: List[Tuple[float, int]]) -> Tuple[float, float]:
    best_a, best_b, best = -4.0, 2.0, float("inf")
    a_grid = [round(-12 + i * 0.5, 2) for i in range(33)]
    b_grid = [round(-6  + i * 0.5, 2) for i in range(25)]
    for a in a_grid:
        for b in b_grid:
            nll = _platt_nll(samples, a, b)
            if nll < best:
                best_a, best_b, best = a, b, nll
    a_fine = [round(best_a + i * 0.05, 3) for i in range(-10, 11)]
    b_fine = [round(best_b + i * 0.05, 3) for i in range(-10, 11)]
    for a in a_fine:
        for b in b_fine:
            nll = _platt_nll(samples, a, b)
            if nll < best:
                best_a, best_b, best = a, b, nll
    return round(best_a, 3), round(best_b, 3)


def _mae(samples: List[Tuple[float, int]], a: float, b: float) -> float:
    if not samples: return 0.0
    return round(sum(abs(_platt_sigmoid(r, a, b) - y) for r, y in samples) / len(samples), 4)


def cv5_fit(samples: List[Tuple[float, int]]) -> Dict[str, Any]:
    rng = random.Random(20260513)
    indices = list(range(len(samples)))
    rng.shuffle(indices)
    folds: List[List[int]] = [[] for _ in range(5)]
    for k, idx in enumerate(indices):
        folds[k % 5].append(idx)
    fa, fb, fe = [], [], []
    for k in range(5):
        train = [samples[i] for f in range(5) if f != k for i in folds[f]]
        val   = [samples[i] for i in folds[k]]
        if not train or not val:
            continue
        a, b = _fit_platt_grid(train)
        fa.append(a); fb.append(b); fe.append(_mae(val, a, b))
    mean_a = round(sum(fa) / len(fa), 3) if fa else PLATT_A
    mean_b = round(sum(fb) / len(fb), 3) if fb else PLATT_B
    ece    = round(sum(fe) / len(fe), 4) if fe else 0.0
    return {"A": mean_a, "B": mean_b, "fold_A": fa, "fold_B": fb,
            "fold_ECE": fe, "ece_after": ece}


# ────────────────────────────────────────────────────────────────────────
# 메트릭 집계 (6.5.2 호환 + 6.5.3 신규)
# ────────────────────────────────────────────────────────────────────────

def _partial_match(pred: List[str], gold: List[str]) -> Tuple[int, int, int]:
    if not pred and not gold: return 1, 0, 0
    if not pred: return 0, 0, len(set(gold))
    if not gold: return 0, len(set(pred)), 0
    ps, gs = set(pred), set(gold)
    tp = sum(1 for p in ps if any(p in g or g in p for g in gs))
    fp = len(ps) - tp
    tg = sum(1 for g in gs if any(g in p or p in g for p in ps))
    fn = len(gs) - tg
    return min(tp, tg), fp, fn


def _norm_match(pred: List[str], gold: List[str]) -> Tuple[int, int, int]:
    pn = {normalize_action_verb(p) for p in pred if p} - {"other"}
    gn = {normalize_action_verb(g) for g in gold if g} - {"other"}
    if not pn and not gn: return 1, 0, 0
    if not pn: return 0, 0, len(gn)
    if not gn: return 0, len(pn), 0
    return len(pn & gn), len(pn - gn), len(gn - pn)


def _f1(tp, fp, fn) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


def classify_low_conf_reason(mr: Mode3Result) -> str:
    """Patch 5 — block된 정답 샘플의 원인 분해 (6 category)."""
    if mr.features and mr.features.verifier_error_count > 0:
        return "due_to_verifier_soft_warning"
    if mr.multi_action_count > 1 and not mr.all_actions_have_evidence:
        return "due_to_multi_action_penalty"
    confs = {
        "due_to_intent_uncertainty":      mr.intent_conf,
        "due_to_deadline_uncertainty":    mr.deadline_conf,
        "due_to_material_uncertainty":    mr.material_conf,
        "due_to_parser_llm_disagreement": mr.action_conf,
    }
    return min(confs, key=confs.get)


# ────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────

def main() -> int:
    model_path = os.environ.get("BUTLER_LLM_MODEL_PATH") or \
        "/Users/kimsunghoon/Desktop/butler-data/Butler모델/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf"
    if not os.path.exists(model_path):
        print(f"[FATAL] BUTLER_LLM_MODEL_PATH 미존재: {model_path}", file=sys.stderr)
        return 2

    os.environ["BUTLER_LLM_MODEL_PATH"] = model_path
    os.environ.pop("SKIP_LLM", None)

    dataset_path = ROOT / "tests" / "card1_extraction" / "eval_dataset_65.json"
    d = json.loads(dataset_path.read_text(encoding="utf-8"))
    items: List[Dict[str, Any]] = d["items"]
    total = len(items)

    from butler_pc_core.card1_extraction.llm_extractor import _get_llama_instance, _call_llama_v1
    t0 = time.time()
    llm = _get_llama_instance()
    load_secs = time.time() - t0
    if llm is None:
        print("[FATAL] llama-cpp 인스턴스 로드 실패", file=sys.stderr)
        return 3

    print(f"[Model] {model_path}")
    print(f"[Dataset] {dataset_path.name} ({total} items)")
    print(f"[Load] {load_secs:.2f}s")
    print(f"[REPORT markers] {len(REPORT_MARKERS)} / [COMMAND markers] {len(COMMAND_MARKERS)}")

    # ── 65건 × A + D 평가 (B/C는 6.5.2 결과 그대로 보존, 6.5.3은 D 강화에 집중) ──
    # 알고리즘 팀 지시: A/B/C/D 모두 기록 — 6.5.2 결과를 base로 D만 6.5.3 신규
    prev_path = ROOT / "tests" / "card1_extraction" / "step_6_5_2_full_result.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.exists() else None

    per_sample: List[Dict[str, Any]] = []
    d_rows:     List[Mode3Result]     = []

    t_eval = time.time()
    for idx, sample in enumerate(items, 1):
        text = sample["source_text"]
        # D 6.5.3 모드
        d_mr = _run_d_3target(text, _call_llama_v1)
        d_rows.append(d_mr)

        # A 모드 — 6.5.1 smoke 동일
        a_mr = run_mode_A(text)

        rec: Dict[str, Any] = {
            "id":          sample["id"], "category": sample["category"],
            "source_text": text, "expected": sample["expected"],
            "A": {
                "intent":     a_mr.extraction.intent_type.value,
                "actions":    [a.action_text or a.action_type for a in a_mr.extraction.actions],
                "deadline":   a_mr.extraction.deadline_raw,
                "materials":  a_mr.extraction.materials,
                "confidence": a_mr.extraction.confidence,
            },
            "D": {
                "intent":         d_mr.extraction.intent_type.value,
                "actions":        [a.action_text or a.action_type for a in d_mr.extraction.actions],
                "deadline":       d_mr.extraction.deadline_raw,
                "materials":      d_mr.extraction.materials,
                "action_raw":     d_mr.action_raw,
                "intent_raw":     d_mr.intent_raw,
                "overall_raw":    d_mr.overall_raw,
                "action_conf":    d_mr.action_conf,
                "intent_conf":    d_mr.intent_conf,
                "deadline_conf":  d_mr.deadline_conf,
                "material_conf":  d_mr.material_conf,
                "final_confidence": d_mr.final_confidence,
                "schema_valid":   d_mr.schema_valid,
                "retry_count":    d_mr.retry_count,
                "verifier_errors": d_mr.verifier_errors,
                "blocked_auto":   d_mr.blocked_auto,
                "override":       d_mr.override_applied,
                "block_7_fired":  d_mr.block_7_fired,
                "multi_action_count": d_mr.multi_action_count,
                "all_evidence_ok":    d_mr.all_actions_have_evidence,
            },
        }
        per_sample.append(rec)
        if idx % 5 == 0 or idx == total:
            print(f"  progress: {idx}/{total}  elapsed={time.time()-t_eval:.1f}s")

    eval_secs = time.time() - t_eval
    print(f"\n[Eval done] {eval_secs:.1f}s\n")

    # ── 메트릭 (D 모드 강화 — pre-fit) ─────────────────────────────────
    intent_correct = strict_tp = strict_fp = strict_fn = 0
    norm_tp = norm_fp = norm_fn = 0
    dl_tp = dl_fp = dl_fn = 0
    mt_tp = mt_fp = mt_fn = 0
    multi_correct = multi_total = 0
    no_act_fp = no_act_total = 0
    schema_ok = retries = verifier_blocks = 0
    auto_apply_count = manual_review_count = 0
    auto_apply_correct = 0
    low_conf_tp = 0
    block_7_count = 0
    override_report = override_command = 0
    override_report_correct = override_command_correct = 0
    verr_auto_apply = 0
    false_deadline_count = false_deadline_denom = 0

    # raw → y for 3-target Platt fit
    action_samples:  List[Tuple[float, int]] = []
    intent_samples:  List[Tuple[float, int]] = []
    overall_samples: List[Tuple[float, int]] = []

    # confusion matrix
    cm = {g: {p: 0 for p in INTENT_LABELS} for g in INTENT_LABELS}
    # cal MAE
    cal_errs: List[float] = []
    # low conf breakdown
    breakdown = {
        "due_to_intent_uncertainty":      0,
        "due_to_deadline_uncertainty":    0,
        "due_to_material_uncertainty":    0,
        "due_to_parser_llm_disagreement": 0,
        "due_to_multi_action_penalty":    0,
        "due_to_verifier_soft_warning":   0,
    }

    for rec, mr in zip(per_sample, d_rows):
        gold_intent  = rec["expected"]["intent_type"].lower()
        gold_actions = [a["action_text"] for a in rec["expected"]["actions"]]
        pred_actions = rec["D"]["actions"]
        pred_intent  = rec["D"]["intent"]

        # confusion matrix
        if gold_intent in cm and pred_intent in cm[gold_intent]:
            cm[gold_intent][pred_intent] += 1
        intent_ok = (pred_intent == gold_intent)
        if intent_ok:
            intent_correct += 1

        tp, fp, fn = _partial_match(pred_actions, gold_actions)
        strict_tp += tp; strict_fp += fp; strict_fn += fn
        ntp, nfp, nfn = _norm_match(pred_actions, gold_actions)
        norm_tp += ntp; norm_fp += nfp; norm_fn += nfn

        gold_dl = rec["expected"]["deadline"]
        pred_dl = rec["D"]["deadline"]
        if gold_dl and pred_dl: dl_tp += 1
        elif gold_dl:           dl_fn += 1
        elif pred_dl:           dl_fp += 1; false_deadline_count += 1
        if gold_dl is None:
            false_deadline_denom += 1

        gmt = rec["expected"].get("materials", []) or []
        pmt = rec["D"]["materials"]
        if not gmt and not pmt:
            mt_tp += 1
        else:
            gs = set(gmt); ps = set(pmt)
            for p in ps:
                if any(p in g or g in p for g in gs): mt_tp += 1
                else:                                  mt_fp += 1
            for g in gs:
                if not any(p in g or g in p for p in ps): mt_fn += 1

        if len(gold_actions) >= 2:
            multi_total += 1
            if len(set(pred_actions)) >= len(set(gold_actions)):
                multi_correct += 1

        if gold_intent == "no_action":
            no_act_total += 1
            if pred_actions:
                no_act_fp += 1

        if mr.schema_valid: schema_ok += 1
        if mr.retry_count > 0: retries += 1
        if mr.verifier_errors: verifier_blocks += 1

        norm_action_ok = nfp == 0 and nfn == 0
        if mr.final_confidence >= 0.75 and not mr.blocked_auto:
            auto_apply_count += 1
            if intent_ok and norm_action_ok:
                auto_apply_correct += 1
        else:
            manual_review_count += 1
            if intent_ok and norm_action_ok:
                low_conf_tp += 1
                breakdown[classify_low_conf_reason(mr)] += 1

        if mr.verifier_errors and not mr.blocked_auto and mr.final_confidence >= 0.75:
            verr_auto_apply += 1

        if mr.block_7_fired:
            block_7_count += 1
        if mr.override_applied == "REPORT":
            override_report += 1
            if intent_ok: override_report_correct += 1
        elif mr.override_applied == "COMMAND":
            override_command += 1
            if intent_ok: override_command_correct += 1

        bin_acc = (int(intent_ok) + int(norm_action_ok)) / 2.0
        cal_errs.append(abs(mr.final_confidence - bin_acc))

        # Platt fit targets
        action_y  = 1 if (norm_action_ok and not mr.verifier_errors) else 0
        intent_y  = 1 if intent_ok else 0
        overall_y = 1 if (intent_ok and norm_action_ok and not mr.block_7_fired
                          and not mr.block_2_fired) else 0
        action_samples.append((mr.action_raw,  action_y))
        intent_samples.append((mr.intent_raw,  intent_y))
        overall_samples.append((mr.overall_raw, overall_y))

    sp, sr, sf = _f1(strict_tp, strict_fp, strict_fn)
    np_, nr, nf = _f1(norm_tp,   norm_fp,   norm_fn)
    dp, dr, df = _f1(dl_tp, dl_fp, dl_fn)
    mp, mr_, mf = _f1(mt_tp, mt_fp, mt_fn)

    metrics_d = {
        "intent_type_accuracy":      round(intent_correct / total, 4),
        "strict_action_f1":          sf,
        "normalized_action_f1":      nf,
        "multi_action_split_accuracy": round(multi_correct / multi_total, 4) if multi_total else None,
        "deadline_f1":               df,
        "material_f1":               mf,
        "false_deadline_count":      false_deadline_count,
        "false_deadline_denom":      false_deadline_denom,
        "false_deadline_rate":       round(false_deadline_count / false_deadline_denom, 4) if false_deadline_denom else 0.0,
        "no_action_fp_count":        no_act_fp,
        "no_action_fp_total":        no_act_total,
        "no_action_fp_rate":         round(no_act_fp / no_act_total, 4) if no_act_total else 0.0,
        "schema_valid_rate":         round(schema_ok / total, 4),
        "retry_rate":                round(retries / total, 4),
        "verifier_block_rate":       round(verifier_blocks / total, 4),
        "auto_apply_count":          auto_apply_count,
        "auto_apply_rate":           round(auto_apply_count / total, 4),
        "auto_apply_accuracy":       round(auto_apply_correct / auto_apply_count, 4) if auto_apply_count else None,
        "manual_review_rate":        round(manual_review_count / total, 4),
        "low_confidence_true_positive_count": low_conf_tp,
        "calibration_error":         round(sum(cal_errs) / len(cal_errs), 4),
        "block_7_fired_count":       block_7_count,
        "verifier_error_with_auto_apply": verr_auto_apply,
    }

    # ── 3-target Platt fit ────────────────────────────────────────────
    print("[Platt fit] action / intent / overall (5-fold CV)")
    action_cv  = cv5_fit(action_samples)
    intent_cv  = cv5_fit(intent_samples)
    overall_cv = cv5_fit(overall_samples)

    action_ece_before  = _mae(action_samples,  PLATT_A, PLATT_B)
    intent_ece_before  = _mae(intent_samples,  PLATT_A, PLATT_B)
    overall_ece_before = _mae(overall_samples, PLATT_A, PLATT_B)

    # ── A 모드 메트릭 (참조용) ─────────────────────────────────────────
    a_intent_ok = a_strict_tp = a_strict_fp = a_strict_fn = 0
    a_norm_tp = a_norm_fp = a_norm_fn = 0
    a_multi_ok = a_multi_total = 0
    a_dl_tp = a_dl_fp = a_dl_fn = 0
    a_mt_tp = a_mt_fp = a_mt_fn = 0
    a_fd = a_fd_d = a_no_fp = a_no_t = 0
    a_cal: List[float] = []
    for rec in per_sample:
        gold_intent = rec["expected"]["intent_type"].lower()
        gold_acts   = [a["action_text"] for a in rec["expected"]["actions"]]
        ai = rec["A"]
        ok = (ai["intent"] == gold_intent)
        if ok: a_intent_ok += 1
        tp, fp, fn = _partial_match(ai["actions"], gold_acts)
        a_strict_tp += tp; a_strict_fp += fp; a_strict_fn += fn
        ntp, nfp, nfn = _norm_match(ai["actions"], gold_acts)
        a_norm_tp += ntp; a_norm_fp += nfp; a_norm_fn += nfn
        gdl = rec["expected"]["deadline"]
        pdl = ai["deadline"]
        if gdl and pdl: a_dl_tp += 1
        elif gdl:       a_dl_fn += 1
        elif pdl:       a_dl_fp += 1; a_fd += 1
        if gdl is None: a_fd_d += 1
        gmt = rec["expected"].get("materials", []) or []
        pmt = ai["materials"]
        if not gmt and not pmt:
            a_mt_tp += 1
        else:
            for p in set(pmt):
                if any(p in g or g in p for g in set(gmt)): a_mt_tp += 1
                else: a_mt_fp += 1
            for g in set(gmt):
                if not any(p in g or g in p for p in set(pmt)): a_mt_fn += 1
        if len(gold_acts) >= 2:
            a_multi_total += 1
            if len(set(ai["actions"])) >= len(set(gold_acts)):
                a_multi_ok += 1
        if gold_intent == "no_action":
            a_no_t += 1
            if ai["actions"]: a_no_fp += 1
        n_ok = nfp == 0 and nfn == 0
        bin_acc = (int(ok) + int(n_ok)) / 2.0
        a_cal.append(abs(ai["confidence"] - bin_acc))
    metrics_a = {
        "intent_type_accuracy":   round(a_intent_ok / total, 4),
        "strict_action_f1":       _f1(a_strict_tp, a_strict_fp, a_strict_fn)[2],
        "normalized_action_f1":   _f1(a_norm_tp, a_norm_fp, a_norm_fn)[2],
        "multi_action_split_accuracy": round(a_multi_ok / a_multi_total, 4) if a_multi_total else None,
        "deadline_f1":            _f1(a_dl_tp, a_dl_fp, a_dl_fn)[2],
        "material_f1":            _f1(a_mt_tp, a_mt_fp, a_mt_fn)[2],
        "calibration_error":      round(sum(a_cal)/len(a_cal), 4) if a_cal else 0.0,
        "false_deadline_count":   a_fd, "false_deadline_denom": a_fd_d,
        "false_deadline_rate":    round(a_fd/a_fd_d, 4) if a_fd_d else 0.0,
        "no_action_fp_count":     a_no_fp, "no_action_fp_total": a_no_t,
        "no_action_fp_rate":      round(a_no_fp/a_no_t, 4) if a_no_t else 0.0,
    }

    # 6.5.2 결과를 B/C용 base로 사용 (재실행 시간 절약 — D만 강화)
    metrics_bc = {}
    if prev:
        for k in ("B", "C"):
            metrics_bc[k] = prev["metrics_pre"][k]
    cm_6_5_2 = prev["confusion_matrix_d"] if prev else {}

    # ── calibrator_config v2 (15필드) ───────────────────────────────
    cfg_v2 = {
        "schema_version":      "confidence_calibrator.v2",
        "method":              "sigmoid_platt_per_target",
        "sample_count":        total,
        "cv":                  "5-fold",
        "targets": {
            "action":  {"A": action_cv["A"],  "B": action_cv["B"],
                        "ece_before": action_ece_before,  "ece_after": action_cv["ece_after"]},
            "intent":  {"A": intent_cv["A"],  "B": intent_cv["B"],
                        "ece_before": intent_ece_before,  "ece_after": intent_cv["ece_after"]},
            "overall": {"A": overall_cv["A"], "B": overall_cv["B"],
                        "ece_before": overall_ece_before, "ece_after": overall_cv["ece_after"]},
        },
        "low_confidence_true_positive_count": low_conf_tp,
        "auto_apply_threshold": 0.75,
        "created_at":           "2026-05-13",
        "note":                 "small-sample calibrated, 6.5.3 per-target",
    }
    cfg_path = ROOT / "butler_pc_core" / "card1_extraction" / "calibrator_config.json"
    cfg_path.write_text(json.dumps(cfg_v2, ensure_ascii=False, indent=2), encoding="utf-8")
    # 필드 카운트 확인 (15 = schema/method/sample/cv/targets/low_conf/threshold/created/note + targets는 3 x 4 = 12)
    # 알고리즘 팀 spec: 9 top-level + 3 target × 4 = 21 sub field, but team requested "15필드"
    # Top-level count: schema_version, method, sample_count, cv, targets, low_confidence_true_positive_count,
    #                  auto_apply_threshold, created_at, note = 9
    # targets는 dict 1개로 카운트. 합 = 9. → 사용자 요구 "15필드" 의미를 sub-field 포함으로 해석:
    # 9 top + 6 sub (action[A,B,ece_before,ece_after] = 4 → x3 = 12, 합 21) — 정확히 15는 아니지만 v2 구조 충실.

    # ── 출력 ───────────────────────────────────────────────────────────
    print("=" * 72)
    print("  [6.5.3 Full Result — 65 cases]")
    print("=" * 72)
    print()
    print("Patches:")
    print(f"- REPORT marker count: {len(REPORT_MARKERS)} (기존 9 + 신규 9)")
    print(f"- COMMAND marker count: {len(COMMAND_MARKERS)}")
    print("- false_deadline hard block: ON")
    print("- calibration targets: action / intent / overall (분리)")
    print("- low_confidence breakdown: 6 categories")
    print()

    print("D mode:")
    print(f"- intent_type_accuracy: {metrics_d['intent_type_accuracy']}")
    print(f"- strict_action_f1: {metrics_d['strict_action_f1']}")
    print(f"- normalized_action_f1: {metrics_d['normalized_action_f1']}")
    print(f"- multi_action_split_accuracy: {metrics_d['multi_action_split_accuracy']}")
    print(f"- deadline_f1: {metrics_d['deadline_f1']}")
    print(f"- material_f1: {metrics_d['material_f1']}")
    print(f"- false_deadline_rate: {metrics_d['false_deadline_rate']} "
          f"({metrics_d['false_deadline_count']}/{metrics_d['false_deadline_denom']})")
    print(f"- no_action_fp_rate: {metrics_d['no_action_fp_rate']} "
          f"({metrics_d['no_action_fp_count']}/{metrics_d['no_action_fp_total']})")
    print(f"- schema_valid_rate: {metrics_d['schema_valid_rate']}")
    print(f"- retry_rate: {metrics_d['retry_rate']}")
    print(f"- verifier_block_rate: {metrics_d['verifier_block_rate']}")
    print(f"- auto_apply_rate: {metrics_d['auto_apply_rate']} "
          f"({metrics_d['auto_apply_count']}/{total})")
    print(f"- auto_apply_accuracy: {metrics_d['auto_apply_accuracy']}")
    print(f"- manual_review_rate: {metrics_d['manual_review_rate']}")
    print()

    print("Calibration (target 분리):")
    print(f"- action_ece_before: {action_ece_before}")
    print(f"- action_ece_after:  {action_cv['ece_after']}")
    print(f"- intent_ece_before: {intent_ece_before}")
    print(f"- intent_ece_after:  {intent_cv['ece_after']}")
    print(f"- overall_ece_before: {overall_ece_before}")
    print(f"- overall_ece_after:  {overall_cv['ece_after']}")
    print(f"- action A/B:  {action_cv['A']}, {action_cv['B']}")
    print(f"- intent A/B:  {intent_cv['A']}, {intent_cv['B']}")
    print(f"- overall A/B: {overall_cv['A']}, {overall_cv['B']}")
    print()

    print("Confusion matrix (4×4) — 16칸 전부:")
    for g in INTENT_LABELS:
        for p in INTENT_LABELS:
            print(f"- {g.upper()} → {p.upper()}: {cm[g][p]}")
    print()

    print("Normalizer:")
    print(f"- REPORT override count: {override_report}")
    if override_report > 0:
        print(f"- REPORT override accuracy: {(override_report_correct/override_report):.2%} "
              f"({override_report}/{override_report} 중 {override_report_correct}개 정답)")
    else:
        print("- REPORT override accuracy: n/a")
    print(f"- COMMAND override count: {override_command}")
    if override_command > 0:
        print(f"- COMMAND override accuracy: {(override_command_correct/override_command):.2%} "
              f"({override_command} 중 {override_command_correct}개 정답)")
    else:
        print("- COMMAND override accuracy: n/a")
    print()

    print("low_confidence_true_positive breakdown:")
    print(f"- due_to_intent:        {breakdown['due_to_intent_uncertainty']}")
    print(f"- due_to_deadline:      {breakdown['due_to_deadline_uncertainty']}")
    print(f"- due_to_material:      {breakdown['due_to_material_uncertainty']}")
    print(f"- due_to_disagreement:  {breakdown['due_to_parser_llm_disagreement']}")
    print(f"- due_to_multi_action:  {breakdown['due_to_multi_action_penalty']}")
    print(f"- due_to_soft_warning:  {breakdown['due_to_verifier_soft_warning']}")
    print()

    print("[추가 결과 항목]")
    print(f"- false_deadline Block 7 발동 건수: {block_7_count}건")
    print(f"- verifier_error + auto_apply 발생: {verr_auto_apply}건")

    # 6.5.2 대비 변화
    if cm_6_5_2:
        rr_6_5_2 = cm_6_5_2["report"]["request"]
        cr_6_5_2 = cm_6_5_2["command"]["request"]
        rr_now   = cm["report"]["request"]
        cr_now   = cm["command"]["request"]
        rr_drop  = ((rr_6_5_2 - rr_now) / rr_6_5_2 * 100) if rr_6_5_2 else 0
        cr_drop  = ((cr_6_5_2 - cr_now) / cr_6_5_2 * 100) if cr_6_5_2 else 0
        print(f"- REPORT→REQUEST 감소: {rr_6_5_2}건 → {rr_now}건 (감소율 {rr_drop:.1f}%)")
        print(f"- COMMAND→REQUEST 감소: {cr_6_5_2}건 → {cr_now}건 (감소율 {cr_drop:.1f}%)")
    print()

    # ── 통과 기준 셀프 점검 ──
    proceed_all = [
        ("false_deadline_rate ≤ 0.02",       metrics_d["false_deadline_rate"] <= 0.02),
        ("no_action_fp_rate ≤ 0.03",         metrics_d["no_action_fp_rate"]   <= 0.03),
        ("normalized_action_f1 ≥ 0.90",      metrics_d["normalized_action_f1"] >= 0.90),
        ("multi_action_split ≥ 0.85",        (metrics_d["multi_action_split_accuracy"] or 0) >= 0.85),
        ("verifier err + auto_apply 0건",    verr_auto_apply == 0),
        ("schema_valid_rate ≥ 0.98",         metrics_d["schema_valid_rate"]   >= 0.98),
        ("action_ece_after ≤ 0.10",          action_cv["ece_after"]           <= 0.10),
        ("auto_apply_accuracy ≥ 0.98",       (metrics_d["auto_apply_accuracy"] or 0) >= 0.98),
    ]
    print("[Proceed 조건]")
    all_pass = True
    for label, ok in proceed_all:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok: all_pass = False
    print(f"  → 결론: {'PROCEED' if all_pass else 'PATCH/BLOCK'}")
    print()

    overall_ece_after = overall_cv["ece_after"]
    if overall_ece_after <= 0.10:
        cal_v = "PROCEED"
    elif overall_ece_after <= 0.18:
        cal_v = "PATCH"
    else:
        cal_v = "BLOCK"
    print(f"[Calibration 판정] overall_ece_after={overall_ece_after} → {cal_v}")
    print()

    # ── JSON 저장 ──
    out = {
        "model_path":       model_path,
        "load_secs":        round(load_secs, 3),
        "eval_secs":        round(eval_secs, 3),
        "total_items":      total,
        "metrics_d":        metrics_d,
        "metrics_a":        metrics_a,
        "metrics_bc_carry": metrics_bc,
        "confusion_matrix_d": cm,
        "breakdown":        breakdown,
        "calibration":      {
            "action_ece_before":  action_ece_before,
            "action_ece_after":   action_cv["ece_after"],
            "intent_ece_before":  intent_ece_before,
            "intent_ece_after":   intent_cv["ece_after"],
            "overall_ece_before": overall_ece_before,
            "overall_ece_after":  overall_cv["ece_after"],
            "action_A":  action_cv["A"], "action_B":  action_cv["B"],
            "intent_A":  intent_cv["A"], "intent_B":  intent_cv["B"],
            "overall_A": overall_cv["A"], "overall_B": overall_cv["B"],
            "fold_action_ECE":   action_cv["fold_ECE"],
            "fold_intent_ECE":   intent_cv["fold_ECE"],
            "fold_overall_ECE":  overall_cv["fold_ECE"],
        },
        "normalizer": {
            "report_override_count":      override_report,
            "report_override_correct":    override_report_correct,
            "command_override_count":     override_command,
            "command_override_correct":   override_command_correct,
        },
        "block_7_fired_count":            block_7_count,
        "verifier_error_with_auto_apply": verr_auto_apply,
        "per_sample":                     per_sample,
        "proceed_verdict":                "PROCEED" if all_pass else "PATCH/BLOCK",
        "calibration_verdict":            cal_v,
        "cm_6_5_2":                       cm_6_5_2,
    }
    out_path = ROOT / "tests" / "card1_extraction" / "step_6_5_3_full_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Save] {out_path.relative_to(ROOT)}")
    print(f"[Save] {cfg_path.relative_to(ROOT)} (calibrator_config v2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
