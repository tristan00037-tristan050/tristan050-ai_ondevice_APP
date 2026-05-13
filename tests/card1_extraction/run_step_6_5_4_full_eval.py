"""단계 6.5.4 — 65건 재평가 (5개 패치 적용 + 4-target component fit).

핵심 변화 (6.5.3 → 6.5.4):
  - Patch A+B: DeadlineType + classify_deadline_candidate
  - Patch C:   verify_deadline (type-aware Block 7)
  - Patch D:   weighted_final_confidence + should_auto_apply (min 폐기)
  - Patch E:   REPORT_MARKERS 22 + component fit (overall reference only)

실행:
  export BUTLER_LLM_MODEL_PATH=".../qwen3-4b-q4_k_m.gguf"
  python tests/card1_extraction/run_step_6_5_4_full_eval.py
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
    weighted_final_confidence, should_auto_apply, AUTO_APPLY_THRESHOLDS,
    COMPONENT_WEIGHTS,
)
from butler_pc_core.card1_extraction.contracts import (
    Card1Extraction, ExtractedAction, IntentType, SentenceType,
)
from butler_pc_core.card1_extraction.deadline_types import (
    DeadlineType, classify_deadline_candidate,
)
from butler_pc_core.card1_extraction.intent_normalizer import (
    REPORT_MARKERS, COMMAND_MARKERS,
    REPORT_OVERRIDE_REASON, COMMAND_OVERRIDE_REASON,
)
from butler_pc_core.card1_extraction.llm_extractor import (
    LLM_EXTRACT_CONFIG, extract_with_llm_v1, V1ExtractResult,
)
from butler_pc_core.card1_extraction.parser import (
    ACTION_VERBS, classify_sentence_type, extract_actions_candidates,
    extract_deadlines, extract_materials,
)
from butler_pc_core.card1_extraction.verifier import (
    apply_hard_rules, verify_deadline,
    BLOCK_FALSE_DEADLINE_NO_EVIDENCE,
    BLOCK_NO_EVIDENCE_DEADLINE, BLOCK_NO_EVIDENCE_MATERIAL,
    BLOCK_NO_EVIDENCE_ACTION, BLOCK_NEGATED_ACTION,
)

from tests.card1_extraction.run_step_6_5_1_smoke import (
    parser_intent_score, parser_deadline_score, parser_material_score,
    parser_action_score, llm_parser_agreement, evidence_coverage,
    negation_risk_of, multi_action_complexity, _action_types,
    _parser_hints_of, _with_confidence, run_mode_A,
)


INTENT_LABELS = ["report", "request", "command", "no_action"]


# ────────────────────────────────────────────────────────────────────────
# D 모드 실행기 (6.5.4 — weighted aggregation + hard gate)
# ────────────────────────────────────────────────────────────────────────

@dataclass
class Mode4Result:
    extraction:        Card1Extraction
    schema_valid:      bool
    retry_count:       int
    retry_reasons:     List[str]              = field(default_factory=list)
    verifier_errors:   List[str]              = field(default_factory=list)
    features:          Optional[ConfidenceFeatures] = None

    action_raw:        float                  = 0.0
    intent_raw:        float                  = 0.0
    overall_raw:       float                  = 0.0
    action_conf:       float                  = 0.0
    intent_conf:       float                  = 0.0
    deadline_conf:     float                  = 0.0
    material_conf:     float                  = 0.0
    final_weighted:    float                  = 0.0
    blocked_auto:      bool                   = False
    auto_apply_ok:     bool                   = False
    auto_apply_reason: str                    = ""

    present_fields:    set                    = field(default_factory=set)
    override_applied:  str                    = ""
    block_7_fired:     bool                   = False
    block_2_fired:     bool                   = False
    block_7_reason:    str                    = ""
    deadline_type:     str                    = "none"
    multi_action_count:int                    = 0


def _run_d_6_5_4(text: str, llm_fn: Callable[[str], str]) -> Mode4Result:
    """D 모드 6.5.4 — type-aware verifier + weighted aggregation + hard gate."""
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

    # override 추출 (llm_extractor._v1_dict_to_extraction이 reason_code에 기록)
    rc = ex.reason_code or ""
    override_kind = ""
    if rc == REPORT_OVERRIDE_REASON:    override_kind = "REPORT"
    elif rc == COMMAND_OVERRIDE_REASON: override_kind = "COMMAND"

    # LLM 출력 deadline에 대한 type 분류 (block 전)
    pre_deadline_raw = ex.deadline_raw
    pre_dtype = classify_deadline_candidate(pre_deadline_raw) if pre_deadline_raw else DeadlineType.NONE

    # 1차 verifier — block 1~4 + block 7 (type-aware)
    verif1 = apply_hard_rules(ex, text, confidence=1.0, schema_valid=True)
    ex_v   = verif1.extraction
    block_7_fired = BLOCK_FALSE_DEADLINE_NO_EVIDENCE in verif1.errors
    block_2_fired = BLOCK_NO_EVIDENCE_MATERIAL       in verif1.errors

    # block 7이 발동했다면 reason 캡처 (어떤 type 이었는지)
    block_7_reason = ""
    if block_7_fired:
        for d in verif1.error_detail:
            if "deadline" in d:
                block_7_reason = d
                break

    # feature 계산
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

    a_raw = action_raw_score(feats, multi_action_count=multi_n,
                             all_actions_have_evidence=all_ev_ok)
    i_raw = intent_raw_score(feats, normalizer_applied=bool(override_kind),
                             normalizer_conflict=False)
    o_raw = overall_raw_score(feats,
                              deadline_ok=not block_7_fired,
                              material_ok=not block_2_fired)

    a_conf = platt_calibrate(a_raw)
    i_conf = platt_calibrate(i_raw)
    d_conf = deadline_confidence_heuristic(feats, block_7_fired=block_7_fired)
    m_conf = material_confidence_heuristic(feats, block_2_fired=block_2_fired)

    # ── 6.5.4 present_fields 결정 ─────────────────────────────────────
    present: set = set()
    if ex_v.deadline_raw:    present.add("deadline")
    if ex_v.materials:       present.add("material")

    components = {
        "action":   a_conf,
        "intent":   i_conf,
        "deadline": d_conf,
        "material": m_conf,
    }

    # hard gate evaluation
    block_1_4_count = sum(
        1 for e in verif1.errors
        if e not in (BLOCK_FALSE_DEADLINE_NO_EVIDENCE,
                     "block_5_auto_apply_low_confidence",
                     "block_6_schema_retry_failed")
    )
    gates = {
        "schema_ok":   v1.schema_valid,
        "verifier_ok": block_1_4_count == 0,
        "evidence_ok": all_ev_ok,
    }

    final_w = weighted_final_confidence(components, present, gates)
    auto_ok, auto_reason = should_auto_apply(components, present, final_w, gates)

    # 2차 verifier — final_weighted 반영 (Block 5/6)
    verif2 = apply_hard_rules(ex_v, text, confidence=final_w, schema_valid=v1.schema_valid)
    ex_final = _with_confidence(verif2.extraction, final_w)

    blocked_auto = (not auto_ok) or verif2.blocked_auto

    return Mode4Result(
        extraction=ex_final, schema_valid=v1.schema_valid,
        retry_count=v1.retry_count, retry_reasons=v1.retry_reasons,
        verifier_errors=verif2.errors, features=feats,
        action_raw=a_raw, intent_raw=i_raw, overall_raw=o_raw,
        action_conf=a_conf, intent_conf=i_conf,
        deadline_conf=d_conf, material_conf=m_conf,
        final_weighted=final_w, blocked_auto=blocked_auto,
        auto_apply_ok=auto_ok, auto_apply_reason=auto_reason,
        present_fields=present, override_applied=override_kind,
        block_7_fired=block_7_fired, block_2_fired=block_2_fired,
        block_7_reason=block_7_reason,
        deadline_type=pre_dtype.value, multi_action_count=multi_n,
    )


# ────────────────────────────────────────────────────────────────────────
# Platt fit helpers (4-target)
# ────────────────────────────────────────────────────────────────────────

def _sigmoid(raw, a, b):
    z = a * raw + b
    if z > 35: return 1e-12
    if z < -35: return 1.0 - 1e-12
    return 1.0 / (1.0 + math.exp(z))


def _nll(samples, a, b):
    eps = 1e-7
    return sum(
        -(y * math.log(min(max(_sigmoid(r, a, b), eps), 1-eps))
          + (1 - y) * math.log(min(max(1 - _sigmoid(r, a, b), eps), 1-eps)))
        for r, y in samples
    )


def _fit_grid(samples):
    if len(samples) < 2:
        return PLATT_A, PLATT_B
    best_a, best_b, best = -4.0, 2.0, float("inf")
    for ai in range(33):
        for bi in range(25):
            a, b = -12 + ai * 0.5, -6 + bi * 0.5
            nll = _nll(samples, a, b)
            if nll < best:
                best_a, best_b, best = a, b, nll
    for ai in range(-10, 11):
        for bi in range(-10, 11):
            a, b = round(best_a + ai * 0.05, 3), round(best_b + bi * 0.05, 3)
            nll = _nll(samples, a, b)
            if nll < best:
                best_a, best_b, best = a, b, nll
    return round(best_a, 3), round(best_b, 3)


def _mae(samples, a, b):
    if not samples: return 0.0
    return round(sum(abs(_sigmoid(r, a, b) - y) for r, y in samples) / len(samples), 4)


def cv5(samples):
    if len(samples) < 5:
        return {"A": PLATT_A, "B": PLATT_B, "ece_after": _mae(samples, PLATT_A, PLATT_B), "n": len(samples)}
    rng = random.Random(20260513)
    idxs = list(range(len(samples)))
    rng.shuffle(idxs)
    folds = [[] for _ in range(5)]
    for k, i in enumerate(idxs):
        folds[k % 5].append(i)
    fa, fb, fe = [], [], []
    for k in range(5):
        train = [samples[i] for f in range(5) if f != k for i in folds[f]]
        val   = [samples[i] for i in folds[k]]
        if not train or not val: continue
        a, b = _fit_grid(train)
        fa.append(a); fb.append(b); fe.append(_mae(val, a, b))
    return {
        "A":         round(sum(fa) / len(fa), 3) if fa else PLATT_A,
        "B":         round(sum(fb) / len(fb), 3) if fb else PLATT_B,
        "ece_after": round(sum(fe) / len(fe), 4) if fe else 0.0,
        "fold_A":    fa, "fold_B": fb, "fold_ECE": fe,
        "n":         len(samples),
    }


def _f1(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    return round(2 * p * r / (p + r) if (p + r) > 0 else 0.0, 4)


def _partial_match(pred, gold):
    if not pred and not gold: return 1, 0, 0
    if not pred: return 0, 0, len(set(gold))
    if not gold: return 0, len(set(pred)), 0
    ps, gs = set(pred), set(gold)
    tp = sum(1 for p in ps if any(p in g or g in p for g in gs))
    fp = len(ps) - tp
    tg = sum(1 for g in gs if any(g in p or p in g for p in ps))
    fn = len(gs) - tg
    return min(tp, tg), fp, fn


def _norm_match(pred, gold):
    pn = {normalize_action_verb(p) for p in pred if p} - {"other"}
    gn = {normalize_action_verb(g) for g in gold if g} - {"other"}
    if not pn and not gn: return 1, 0, 0
    if not pn: return 0, 0, len(gn)
    if not gn: return 0, len(pn), 0
    return len(pn & gn), len(pn - gn), len(gn - pn)


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
        print("[FATAL] llama-cpp 로드 실패", file=sys.stderr); return 3

    print(f"[Model] {model_path}")
    print(f"[Dataset] {dataset_path.name} ({total} items)")
    print(f"[Load] {load_secs:.2f}s")
    print(f"[REPORT markers] {len(REPORT_MARKERS)}  /  [COMMAND markers] {len(COMMAND_MARKERS)}")
    print(f"[AUTO_APPLY_THRESHOLDS] {AUTO_APPLY_THRESHOLDS}")

    # 6.5.3 결과 carry-over (B/C)
    prev_path = ROOT / "tests" / "card1_extraction" / "step_6_5_2_full_result.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.exists() else None

    per_sample: List[Dict[str, Any]] = []
    d_rows:     List[Mode4Result]     = []

    t_eval = time.time()
    for idx, sample in enumerate(items, 1):
        text = sample["source_text"]
        d_mr = _run_d_6_5_4(text, _call_llama_v1)
        d_rows.append(d_mr)
        a_mr = run_mode_A(text)

        rec = {
            "id": sample["id"], "category": sample["category"],
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
                "final_weighted": d_mr.final_weighted,
                "schema_valid":   d_mr.schema_valid,
                "retry_count":    d_mr.retry_count,
                "verifier_errors": d_mr.verifier_errors,
                "blocked_auto":   d_mr.blocked_auto,
                "auto_apply_ok":  d_mr.auto_apply_ok,
                "auto_apply_reason": d_mr.auto_apply_reason,
                "present_fields": sorted(d_mr.present_fields),
                "override":       d_mr.override_applied,
                "block_7_fired":  d_mr.block_7_fired,
                "block_7_reason": d_mr.block_7_reason,
                "deadline_type":  d_mr.deadline_type,
                "multi_action_count": d_mr.multi_action_count,
            },
        }
        per_sample.append(rec)
        if idx % 5 == 0 or idx == total:
            print(f"  progress: {idx}/{total}  elapsed={time.time()-t_eval:.1f}s")

    eval_secs = time.time() - t_eval
    print(f"\n[Eval done] {eval_secs:.1f}s\n")

    # ── 메트릭 D ────────────────────────────────────────────────────────
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
    deadline_inquiry_block = urgency_block = condition_block = 0
    override_report = override_command = 0
    override_report_correct = override_command_correct = 0
    verr_auto_apply = 0
    false_deadline_count = false_deadline_denom = 0

    action_samples:  List[Tuple[float, int]] = []
    intent_samples:  List[Tuple[float, int]] = []
    deadline_samples: List[Tuple[float, int]] = []   # present only
    material_samples: List[Tuple[float, int]] = []   # present only
    overall_samples: List[Tuple[float, int]] = []    # reference

    cm = {g: {p: 0 for p in INTENT_LABELS} for g in INTENT_LABELS}

    for rec, mr in zip(per_sample, d_rows):
        gold_intent  = rec["expected"]["intent_type"].lower()
        gold_actions = [a["action_text"] for a in rec["expected"]["actions"]]
        gold_dl      = rec["expected"]["deadline"]
        gold_mat     = rec["expected"].get("materials", []) or []
        pred_actions = rec["D"]["actions"]
        pred_intent  = rec["D"]["intent"]
        pred_dl      = rec["D"]["deadline"]
        pred_mat     = rec["D"]["materials"]

        if gold_intent in cm and pred_intent in cm[gold_intent]:
            cm[gold_intent][pred_intent] += 1
        intent_ok = (pred_intent == gold_intent)
        if intent_ok: intent_correct += 1

        tp, fp, fn = _partial_match(pred_actions, gold_actions)
        strict_tp += tp; strict_fp += fp; strict_fn += fn
        ntp, nfp, nfn = _norm_match(pred_actions, gold_actions)
        norm_tp += ntp; norm_fp += nfp; norm_fn += nfn

        if gold_dl and pred_dl: dl_tp += 1
        elif gold_dl:           dl_fn += 1
        elif pred_dl:           dl_fp += 1; false_deadline_count += 1
        if gold_dl is None:
            false_deadline_denom += 1

        if not gold_mat and not pred_mat:
            mt_tp += 1
        else:
            gs = set(gold_mat); ps = set(pred_mat)
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
            if pred_actions: no_act_fp += 1

        if mr.schema_valid: schema_ok += 1
        if mr.retry_count > 0: retries += 1
        if mr.verifier_errors: verifier_blocks += 1

        norm_action_ok = nfp == 0 and nfn == 0
        if mr.auto_apply_ok:
            auto_apply_count += 1
            if intent_ok and norm_action_ok:
                auto_apply_correct += 1
        else:
            manual_review_count += 1
            if intent_ok and norm_action_ok:
                low_conf_tp += 1

        if mr.verifier_errors and mr.auto_apply_ok:
            verr_auto_apply += 1

        # Block 7 type counters
        if mr.block_7_fired:
            r = mr.block_7_reason or ""
            if "deadline_inquiry" in r: deadline_inquiry_block += 1
            elif "urgency"        in r: urgency_block          += 1
            elif "condition"      in r: condition_block        += 1

        if mr.override_applied == "REPORT":
            override_report += 1
            if intent_ok: override_report_correct += 1
        elif mr.override_applied == "COMMAND":
            override_command += 1
            if intent_ok: override_command_correct += 1

        # Platt fit targets
        action_y  = 1 if (norm_action_ok and not any(
            e for e in mr.verifier_errors
            if e in (BLOCK_NO_EVIDENCE_ACTION, BLOCK_NEGATED_ACTION)
        )) else 0
        intent_y  = 1 if intent_ok else 0
        overall_y = 1 if (intent_ok and norm_action_ok and not mr.block_7_fired
                          and not mr.block_2_fired) else 0
        action_samples.append((mr.action_raw,  action_y))
        intent_samples.append((mr.intent_raw,  intent_y))
        overall_samples.append((mr.overall_raw, overall_y))

        # deadline_present fit — gold deadline 있는 샘플만
        if gold_dl is not None:
            dl_match = bool(pred_dl) and pred_dl == gold_dl
            deadline_samples.append((mr.deadline_conf, 1 if dl_match else 0))

        # material_present fit — gold material 있는 샘플만
        if gold_mat:
            mt_match = bool(pred_mat) and any(p in g or g in p
                                              for p in pred_mat for g in gold_mat)
            material_samples.append((mr.material_conf, 1 if mt_match else 0))

    sf = _f1(strict_tp, strict_fp, strict_fn)
    nf = _f1(norm_tp,   norm_fp,   norm_fn)
    df = _f1(dl_tp,     dl_fp,     dl_fn)
    mf = _f1(mt_tp,     mt_fp,     mt_fn)

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
        "verifier_error_with_auto_apply": verr_auto_apply,
    }

    # ── 4-target Platt fit ───────────────────────────────────────────
    print(f"[Platt fit] action({len(action_samples)}) / intent({len(intent_samples)}) "
          f"/ deadline_present({len(deadline_samples)}) / material_present({len(material_samples)})")
    action_ece_before    = _mae(action_samples,   PLATT_A, PLATT_B)
    intent_ece_before    = _mae(intent_samples,   PLATT_A, PLATT_B)
    deadline_ece_before  = _mae(deadline_samples, PLATT_A, PLATT_B) if deadline_samples else 0.0
    material_ece_before  = _mae(material_samples, PLATT_A, PLATT_B) if material_samples else 0.0
    overall_ece_before   = _mae(overall_samples,  PLATT_A, PLATT_B)

    action_cv   = cv5(action_samples)
    intent_cv   = cv5(intent_samples)
    deadline_cv = cv5(deadline_samples)
    material_cv = cv5(material_samples)
    overall_ece_ref = _mae(overall_samples, PLATT_A, PLATT_B)  # reference only

    # ── A 모드 (참고용) ─────────────────────────────────────────────
    a_correct = 0
    a_strict_tp = a_strict_fp = a_strict_fn = 0
    a_norm_tp = a_norm_fp = a_norm_fn = 0
    for rec in per_sample:
        gi = rec["expected"]["intent_type"].lower()
        ga = [a["action_text"] for a in rec["expected"]["actions"]]
        ai = rec["A"]
        if ai["intent"] == gi: a_correct += 1
        tp, fp, fn = _partial_match(ai["actions"], ga)
        a_strict_tp += tp; a_strict_fp += fp; a_strict_fn += fn
        ntp, nfp, nfn = _norm_match(ai["actions"], ga)
        a_norm_tp += ntp; a_norm_fp += nfp; a_norm_fn += nfn

    metrics_a = {
        "intent_type_accuracy":   round(a_correct / total, 4),
        "strict_action_f1":       _f1(a_strict_tp, a_strict_fp, a_strict_fn),
        "normalized_action_f1":   _f1(a_norm_tp, a_norm_fp, a_norm_fn),
    }

    cm_6_5_3 = (json.loads((ROOT / "tests" / "card1_extraction" / "step_6_5_3_full_result.json").read_text(encoding="utf-8"))
                .get("confusion_matrix_d", {}))

    # ── calibrator_config v3 ───────────────────────────────────────
    cfg_v3 = {
        "schema_version": "confidence_calibrator.v3",
        "method":         "sigmoid_platt_per_component",
        "sample_count":   total,
        "cv":             "5-fold",
        "targets": {
            "action": {"A": action_cv["A"], "B": action_cv["B"],
                       "ece_before": action_ece_before, "ece_after": action_cv["ece_after"]},
            "intent": {"A": intent_cv["A"], "B": intent_cv["B"],
                       "ece_before": intent_ece_before, "ece_after": intent_cv["ece_after"]},
            "deadline_present": {"A": deadline_cv["A"], "B": deadline_cv["B"],
                                 "ece_before": deadline_ece_before, "ece_after": deadline_cv["ece_after"],
                                 "n_present": deadline_cv["n"]},
            "material_present": {"A": material_cv["A"], "B": material_cv["B"],
                                 "ece_before": material_ece_before, "ece_after": material_cv["ece_after"],
                                 "n_present": material_cv["n"]},
        },
        "overall_ece_reference_only":         overall_ece_ref,
        "auto_apply_threshold":               AUTO_APPLY_THRESHOLDS,
        "low_confidence_true_positive_count": low_conf_tp,
        "created_at":                         "2026-05-13",
        "note":                               "small-sample calibrated, 6.5.4 component-fit",
    }
    cfg_path = ROOT / "butler_pc_core" / "card1_extraction" / "calibrator_config.json"
    cfg_path.write_text(json.dumps(cfg_v3, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 출력 ────────────────────────────────────────────────────────
    print("=" * 72)
    print("  [6.5.4 Full Result — 65 cases]")
    print("=" * 72)
    print()
    print("Patches:")
    print("- deadline_disqualifier: ON (3 patterns)")
    print("- confidence_aggregation: hard gate + weighted (min 폐기)")
    print(f"- report_markers_added: {len(REPORT_MARKERS)} (기존 18 + 신규 4)")
    print("- calibration_policy: component fit (overall reference only)")
    print()
    print("[필수 확인 9개 — 알고리즘 팀 즉시 판정 영역]")
    print(f"1. false_deadline_remaining:           {false_deadline_count}건")
    print(f"2. deadline_inquiry_block_count:       {deadline_inquiry_block}건")
    print(f"3. urgency_as_deadline_block_count:    {urgency_block}건")
    print(f"4. condition_as_deadline_block_count:  {condition_block}건")
    print(f"5. auto_apply_rate:                    {metrics_d['auto_apply_rate']}")
    print(f"6. auto_apply_accuracy:                {metrics_d['auto_apply_accuracy']}")
    print(f"7. verifier_error_auto_apply_count:    {verr_auto_apply}건")
    print(f"8. action_ece_after:                   {action_cv['ece_after']}")
    print(f"9. intent_ece_after:                   {intent_cv['ece_after']}")
    print(f"   overall_ece_reference_only:         {overall_ece_ref}")
    print()

    print("D mode:")
    for k in ("intent_type_accuracy","strict_action_f1","normalized_action_f1",
              "multi_action_split_accuracy","deadline_f1","material_f1",
              "false_deadline_rate","no_action_fp_rate","schema_valid_rate",
              "retry_rate","verifier_block_rate","auto_apply_rate",
              "auto_apply_accuracy","manual_review_rate"):
        print(f"- {k}: {metrics_d[k]}")
    print()

    print("Deadline:")
    print(f"- deadline_inquiry_block_count:       {deadline_inquiry_block}")
    print(f"- urgency_as_deadline_block_count:    {urgency_block}")
    print(f"- condition_as_deadline_block_count:  {condition_block}")
    print(f"- false_deadline_remaining:           {false_deadline_count}")
    print()

    print("Calibration:")
    print(f"- action_ece_before:   {action_ece_before}")
    print(f"- action_ece_after:    {action_cv['ece_after']}")
    print(f"- intent_ece_before:   {intent_ece_before}")
    print(f"- intent_ece_after:    {intent_cv['ece_after']}")
    print(f"- deadline_present_ece_before: {deadline_ece_before}")
    print(f"- deadline_present_ece_after:  {deadline_cv['ece_after']}")
    print(f"- material_ece_before: {material_ece_before}")
    print(f"- material_ece_after:  {material_cv['ece_after']}")
    print(f"- overall_ece_reference_only: {overall_ece_ref}")
    print()

    print("Confusion matrix (4x4) — 16칸 전부:")
    for g in INTENT_LABELS:
        for p in INTENT_LABELS:
            print(f"- {g.upper()} → {p.upper()}: {cm[g][p]}")
    print()

    print("Normalizer:")
    print(f"- REPORT override count: {override_report}")
    if override_report > 0:
        print(f"- REPORT override accuracy: {(override_report_correct/override_report):.2%} ({override_report_correct}/{override_report})")
    else:
        print(f"- REPORT override accuracy: n/a")
    print(f"- COMMAND override count: {override_command}")
    if override_command > 0:
        print(f"- COMMAND override accuracy: {(override_command_correct/override_command):.2%} ({override_command_correct}/{override_command})")
    else:
        print(f"- COMMAND override accuracy: n/a")
    print()

    # Patch 효과 측정 (6.5.3 → 6.5.4)
    print("Patch 효과 측정 (6.5.3 → 6.5.4):")
    print(f"- false_deadline_rate: 0.0789 → {metrics_d['false_deadline_rate']}")
    print(f"- auto_apply_rate: 0.0 → {metrics_d['auto_apply_rate']}")
    print(f"- auto_apply_accuracy: None → {metrics_d['auto_apply_accuracy']}")
    if cm_6_5_3:
        rr_prev = cm_6_5_3["report"]["request"]
        cr_prev = cm_6_5_3["command"]["request"]
        rr_now  = cm["report"]["request"]
        cr_now  = cm["command"]["request"]
        print(f"- REPORT→REQUEST 잔여: {rr_prev} → {rr_now}")
        print(f"- COMMAND→REQUEST 잔여: {cr_prev} → {cr_now} (유지 영역)")
    print(f"- intent_type_accuracy: 0.7692 → {metrics_d['intent_type_accuracy']}")
    print()

    # 가장 먼저 볼 항목 3개
    block_2 = next((r for r in per_sample if r["id"] == "card1_002"), None)
    block_23 = next((r for r in per_sample if r["id"] == "card1_023"), None)
    block_39 = next((r for r in per_sample if r["id"] == "card1_039"), None)
    print("가장 먼저 볼 항목 3개 — 결과:")
    print("1. false_deadline 3건 차단:")
    for tag, r in (("card1_002 DEADLINE_INQUIRY", block_2),
                   ("card1_023 URGENCY",          block_23),
                   ("card1_039 CONDITION",        block_39)):
        if r:
            d_dl = r["D"]["deadline"]
            block_fired = r["D"]["block_7_fired"]
            ok = (not d_dl) or block_fired
            print(f"   - {tag}: {'차단' if ok else '미차단'}  "
                  f"(deadline={d_dl!r}, block_7={block_fired}, type={r['D']['deadline_type']})")
    print(f"2. auto_apply_rate >= 0.30 회복: {metrics_d['auto_apply_rate']} "
          f"{'PASS' if metrics_d['auto_apply_rate'] >= 0.30 else 'FAIL'}")
    aa = metrics_d['auto_apply_accuracy']
    print(f"3. auto_apply_accuracy >= 0.98 유지: {aa} "
          f"{'PASS' if (aa is not None and aa >= 0.98) else 'FAIL'}")
    print()

    # Proceed 자동 판정
    proceed_all = [
        ("false_deadline_rate ≤ 0.02",     metrics_d["false_deadline_rate"] <= 0.02),
        ("기존 3건 모두 block/제거",         all(((not r["D"]["deadline"]) or r["D"]["block_7_fired"])
                                                for r in (block_2, block_23, block_39) if r)),
        ("normalized_action_f1 ≥ 0.90",   metrics_d["normalized_action_f1"] >= 0.90),
        ("multi_action_split ≥ 0.85",     (metrics_d["multi_action_split_accuracy"] or 0) >= 0.85),
        ("no_action_fp_rate = 0",         metrics_d["no_action_fp_rate"] == 0),
        ("schema_valid_rate ≥ 0.98",      metrics_d["schema_valid_rate"] >= 0.98),
        ("verifier err + auto_apply = 0", verr_auto_apply == 0),
        ("action_ece_after ≤ 0.10",       action_cv["ece_after"] <= 0.10),
        ("auto_apply_accuracy ≥ 0.98",    (metrics_d["auto_apply_accuracy"] or 0) >= 0.98),
        ("auto_apply_rate ≥ 0.30",        metrics_d["auto_apply_rate"] >= 0.30),
    ]
    print("[Proceed 조건]")
    all_pass = True
    for label, ok in proceed_all:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok: all_pass = False
    verdict = "PROCEED" if all_pass else "PATCH/BLOCK"
    print(f"  → 결론: {verdict}")
    print()

    # ── JSON 저장 ──────────────────────────────────────────────────
    out = {
        "model_path":            model_path,
        "load_secs":             round(load_secs, 3),
        "eval_secs":             round(eval_secs, 3),
        "total_items":           total,
        "metrics_d":             metrics_d,
        "metrics_a":             metrics_a,
        "confusion_matrix_d":    cm,
        "calibration": {
            "action_ece_before":           action_ece_before,
            "action_ece_after":            action_cv["ece_after"],
            "intent_ece_before":           intent_ece_before,
            "intent_ece_after":            intent_cv["ece_after"],
            "deadline_present_ece_before": deadline_ece_before,
            "deadline_present_ece_after":  deadline_cv["ece_after"],
            "material_ece_before":         material_ece_before,
            "material_ece_after":          material_cv["ece_after"],
            "overall_ece_reference_only":  overall_ece_ref,
            "action_A":   action_cv["A"],   "action_B":   action_cv["B"],
            "intent_A":   intent_cv["A"],   "intent_B":   intent_cv["B"],
            "deadline_A": deadline_cv["A"], "deadline_B": deadline_cv["B"],
            "material_A": material_cv["A"], "material_B": material_cv["B"],
        },
        "deadline_block_breakdown": {
            "deadline_inquiry":            deadline_inquiry_block,
            "urgency_as_deadline":         urgency_block,
            "condition_as_deadline":       condition_block,
            "false_deadline_remaining":    false_deadline_count,
        },
        "normalizer": {
            "report_override_count":    override_report,
            "report_override_correct":  override_report_correct,
            "command_override_count":   override_command,
            "command_override_correct": override_command_correct,
        },
        "cm_6_5_3":              cm_6_5_3,
        "per_sample":            per_sample,
        "proceed_verdict":       verdict,
    }
    out_path = ROOT / "tests" / "card1_extraction" / "step_6_5_4_full_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Save] {out_path.relative_to(ROOT)}")
    print(f"[Save] {cfg_path.relative_to(ROOT)} (calibrator_config v3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
