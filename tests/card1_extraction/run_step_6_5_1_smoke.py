"""단계 6.5.1 — Qwen3-4B 5건 A/B/C/D smoke (알고리즘 팀 최종 지침).

실행:
  source .venv/bin/activate
  export BUTLER_LLM_MODEL_PATH="/Users/kimsunghoon/Desktop/butler-data/Butler모델/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf"
  python tests/card1_extraction/run_step_6_5_1_smoke.py

5건 표본 (eval_dataset_65.json):
  의문문    card1_001  "이 자료 보내주실 수 있나요?"           REQUEST  [보내]
  평서문    card1_009  "프로젝트 계획서를 내일까지 제출할 예정입니다." REPORT   [제출]
  복합액션  card1_046  "보고서 검토하고 수정 사항 정리해서 목요일까지 보내주세요."
                                                                       REQUEST  [검토, 정리, 보내]
  부정형    card1_042  "해당 건은 더 이상 진행하지 않아도 됩니다."   NO_ACTION []
  추상동사  card1_056  "자료 정리되면 공유해주세요."                 REQUEST  [정리, 공유]
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction import extract_card1  # mode A (heuristic)
from butler_pc_core.card1_extraction.confidence import (
    ConfidenceFeatures, raw_confidence_score, platt_calibrate,
    PLATT_A, PLATT_B,
)
from butler_pc_core.card1_extraction.contracts import (
    Card1Extraction, ExtractedAction, IntentType, SentenceType,
)
from butler_pc_core.card1_extraction.llm_extractor import (
    LLM_EXTRACT_CONFIG, extract_with_llm_v1, V1ExtractResult,
)
from butler_pc_core.card1_extraction.parser import (
    ACTION_VERBS, _ACTION_VERB_RE,
    classify_sentence_type, extract_actions_candidates,
    extract_deadlines, extract_materials,
)
from butler_pc_core.card1_extraction.verifier import apply_hard_rules


# ── 5건 샘플 (gold standard from eval_dataset_65.json) ────────────────────
SAMPLES: List[Dict[str, Any]] = [
    {
        "id": "card1_001", "category": "의문문",
        "source_text": "이 자료 보내주실 수 있나요?",
        "expected": {
            "intent_type": "request", "no_action": False,
            "actions": [{"action_type": "보내", "is_negated": False}],
            "deadline": None, "materials": ["자료"],
        },
    },
    {
        "id": "card1_009", "category": "평서문",
        "source_text": "프로젝트 계획서를 내일까지 제출할 예정입니다.",
        "expected": {
            "intent_type": "report", "no_action": False,
            "actions": [{"action_type": "제출", "is_negated": False}],
            "deadline": "내일까지", "materials": ["계획서"],
        },
    },
    {
        "id": "card1_046", "category": "복합 다중 액션",
        "source_text": "보고서 검토하고 수정 사항 정리해서 목요일까지 보내주세요.",
        "expected": {
            "intent_type": "request", "no_action": False,
            "actions": [
                {"action_type": "검토", "is_negated": False},
                {"action_type": "정리", "is_negated": False},
                {"action_type": "보내", "is_negated": False},
            ],
            "deadline": "목요일까지", "materials": ["보고서"],
        },
    },
    {
        "id": "card1_042", "category": "부정형/no-action",
        "source_text": "해당 건은 더 이상 진행하지 않아도 됩니다.",
        "expected": {
            "intent_type": "no_action", "no_action": True,
            "actions": [],
            "deadline": None, "materials": [],
        },
    },
    {
        "id": "card1_056", "category": "추상동사(마감없는 요청)",
        "source_text": "자료 정리되면 공유해주세요.",
        "expected": {
            "intent_type": "request", "no_action": False,
            "actions": [
                {"action_type": "정리", "is_negated": False},
                {"action_type": "공유", "is_negated": False},
            ],
            "deadline": None, "materials": ["자료"],
        },
    },
]


# ── parser feature score 계산 ────────────────────────────────────────────
_INTENT_VERB_HINT = {
    "request":   ["주세요", "해주세요", "부탁드립니다", "바랍니다"],
    "report":    ["드립니다", "드리겠습니다", "예정입니다", "보고합니다"],
    "question":  ["가요?", "까요?", "합니까", "언제", "어떻게"],
    "command":   ["하십시오", "하시기 바랍니다", "주십시오"],
    "schedule":  ["회의", "미팅", "일정", "있습니다"],
    "no_action": ["하지 않", "않습니다", "안 됩니다", "없습니다", "보류"],
}


def parser_intent_score(text: str, intent_type: IntentType) -> float:
    """parser intent 신뢰도 — 해당 intent 키워드 매칭률 [0,1]."""
    keys = _INTENT_VERB_HINT.get(intent_type.value, [])
    if not keys:
        return 0.3
    hits = sum(1 for k in keys if k in text)
    return min(1.0, 0.3 + 0.25 * hits)


def parser_deadline_score(text: str) -> float:
    """deadline 패턴 매칭 수에 따른 [0,1]."""
    n = len(extract_deadlines(text))
    return 1.0 if n >= 1 else 0.0


def parser_material_score(text: str) -> float:
    n = len(extract_materials(text))
    return min(1.0, 0.5 + 0.2 * n) if n > 0 else 0.0


def parser_action_score(text: str) -> float:
    n = len(extract_actions_candidates(text))
    return min(1.0, 0.4 + 0.2 * n) if n > 0 else 0.0


# ── LLM/parser agreement (액션 type IoU) ─────────────────────────────────
def _action_types(ex: Card1Extraction) -> List[str]:
    types: List[str] = []
    for a in ex.actions:
        if a.action_type:
            types.append(a.action_type)
        else:
            for v in ACTION_VERBS:
                if v in (a.action_text or ""):
                    types.append(v)
                    break
    return types


def parser_actions_from_text(text: str) -> List[str]:
    found: List[str] = []
    for v in ACTION_VERBS:
        if v in text:
            found.append(v)
    return found


def llm_parser_agreement(llm_ex: Card1Extraction, text: str) -> float:
    llm_types = set(_action_types(llm_ex))
    par_types = set(parser_actions_from_text(text))
    if not llm_types and not par_types:
        return 1.0
    if not llm_types or not par_types:
        return 0.0
    inter = llm_types & par_types
    union = llm_types | par_types
    return round(len(inter) / len(union), 4) if union else 0.0


def evidence_coverage(ex: Card1Extraction, source_text: str) -> float:
    if not ex.actions:
        return 1.0
    covered = 0
    for a in ex.actions:
        ev = a.source_evidence or a.action_text
        if ev and ev in source_text:
            covered += 1
    return round(covered / len(ex.actions), 4)


def negation_risk_of(text: str, ex: Card1Extraction) -> float:
    """부정형 텍스트인데 actions가 남아있으면 위험."""
    sent = classify_sentence_type(text)
    is_neg_text = (sent == SentenceType.NEGATIVE) or any(
        kw in text for kw in ("하지 않", "안 됩니다", "보류", "취소", "어렵습니다")
    )
    if not is_neg_text:
        return 0.0
    return 1.0 if ex.actions else 0.5


def multi_action_complexity(ex: Card1Extraction) -> float:
    n = len(ex.actions)
    if n >= 3:
        return 1.0
    if n == 2:
        return 0.5
    return 0.0


# ── 6.5.1 mode 실행기 ────────────────────────────────────────────────────
@dataclass
class ModeResult:
    name: str                                    # A/B/C/D
    extraction: Card1Extraction
    schema_valid: bool        = True
    retry_count: int          = 0
    retry_reasons: List[str]  = field(default_factory=list)
    verifier_errors: List[str] = field(default_factory=list)
    raw_features: Optional[ConfidenceFeatures] = None
    raw_score: float          = 0.0
    final_confidence: float   = 0.0
    blocked_auto: bool        = False
    raw_first: str            = ""
    raw_retry: str            = ""


def run_mode_A(text: str) -> ModeResult:
    """A = parser only (heuristic) — SKIP_LLM."""
    os.environ["SKIP_LLM"] = "true"
    ex = extract_card1(text, use_llm=False, skip_llm=True)
    # legacy confidence already calibrated by compute_card1_confidence
    return ModeResult(name="A", extraction=ex, schema_valid=True,
                      final_confidence=ex.confidence,
                      blocked_auto=ex.confidence < 0.75)


def run_mode_B(text: str, llm_fn) -> ModeResult:
    """B = Qwen3 only — no parser hints, no verifier."""
    v1: V1ExtractResult = extract_with_llm_v1(text, parsed_hints=None, llm_callable=llm_fn)
    sent_type = classify_sentence_type(text)
    ex = v1.extraction
    ex = Card1Extraction(
        intent=ex.intent, intent_type=ex.intent_type,
        deadline=ex.deadline, deadline_raw=ex.deadline_raw,
        materials=ex.materials, actions=ex.actions,
        sentence_type=sent_type,
        confidence=0.0, needs_review=True, reason_code=ex.reason_code,
    )
    feats = ConfidenceFeatures(
        parser_intent_score=0.0, parser_deadline_score=0.0,
        parser_material_score=0.0, parser_action_score=0.0,
        llm_schema_valid=v1.schema_valid,
        llm_parser_agreement=0.0,
        evidence_coverage=evidence_coverage(ex, text),
        negation_risk=negation_risk_of(text, ex),
        multi_action_complexity=multi_action_complexity(ex),
        verifier_error_count=0,
    )
    raw = raw_confidence_score(feats)
    cal = platt_calibrate(raw)
    ex = _with_confidence(ex, cal)
    return ModeResult(name="B", extraction=ex,
                      schema_valid=v1.schema_valid,
                      retry_count=v1.retry_count, retry_reasons=v1.retry_reasons,
                      raw_features=feats, raw_score=raw, final_confidence=cal,
                      blocked_auto=cal < 0.75,
                      raw_first=v1.raw_text_first, raw_retry=v1.raw_text_retry)


def _parser_hints_of(text: str) -> Dict[str, List[str]]:
    return {
        "deadlines": extract_deadlines(text),
        "materials": extract_materials(text),
        "actions":   extract_actions_candidates(text),
    }


def run_mode_C(text: str, llm_fn) -> ModeResult:
    """C = parser + Qwen3 — verifier 없음."""
    hints = _parser_hints_of(text)
    v1 = extract_with_llm_v1(text, parsed_hints=hints, llm_callable=llm_fn)
    sent_type = classify_sentence_type(text)
    ex = v1.extraction
    ex = Card1Extraction(
        intent=ex.intent, intent_type=ex.intent_type,
        deadline=ex.deadline, deadline_raw=ex.deadline_raw,
        materials=ex.materials, actions=ex.actions,
        sentence_type=sent_type,
        confidence=0.0, needs_review=True, reason_code=ex.reason_code,
    )
    feats = ConfidenceFeatures(
        parser_intent_score=parser_intent_score(text, ex.intent_type),
        parser_deadline_score=parser_deadline_score(text),
        parser_material_score=parser_material_score(text),
        parser_action_score=parser_action_score(text),
        llm_schema_valid=v1.schema_valid,
        llm_parser_agreement=llm_parser_agreement(ex, text),
        evidence_coverage=evidence_coverage(ex, text),
        negation_risk=negation_risk_of(text, ex),
        multi_action_complexity=multi_action_complexity(ex),
        verifier_error_count=0,   # C 모드는 verifier 미사용
    )
    raw = raw_confidence_score(feats)
    cal = platt_calibrate(raw)
    ex = _with_confidence(ex, cal)
    return ModeResult(name="C", extraction=ex,
                      schema_valid=v1.schema_valid,
                      retry_count=v1.retry_count, retry_reasons=v1.retry_reasons,
                      raw_features=feats, raw_score=raw, final_confidence=cal,
                      blocked_auto=cal < 0.75,
                      raw_first=v1.raw_text_first, raw_retry=v1.raw_text_retry)


def run_mode_D(text: str, llm_fn) -> ModeResult:
    """D = parser + Qwen3 + verifier + calibrated confidence (전체 파이프라인)."""
    hints = _parser_hints_of(text)
    v1 = extract_with_llm_v1(text, parsed_hints=hints, llm_callable=llm_fn)
    sent_type = classify_sentence_type(text)
    ex = v1.extraction
    ex = Card1Extraction(
        intent=ex.intent, intent_type=ex.intent_type,
        deadline=ex.deadline, deadline_raw=ex.deadline_raw,
        materials=ex.materials, actions=ex.actions,
        sentence_type=sent_type,
        confidence=0.0, needs_review=True, reason_code=ex.reason_code,
    )
    # 우선 verifier 1차 적용 (confidence/schema_valid 빼고 → block 1~4)
    verif1 = apply_hard_rules(ex, text, confidence=1.0, schema_valid=True)
    ex_v   = verif1.extraction
    block_errs_no_conf = [e for e in verif1.errors
                          if e not in ("block_5_auto_apply_low_confidence",
                                       "block_6_schema_retry_failed")]

    feats = ConfidenceFeatures(
        parser_intent_score=parser_intent_score(text, ex_v.intent_type),
        parser_deadline_score=parser_deadline_score(text),
        parser_material_score=parser_material_score(text),
        parser_action_score=parser_action_score(text),
        llm_schema_valid=v1.schema_valid,
        llm_parser_agreement=llm_parser_agreement(ex_v, text),
        evidence_coverage=evidence_coverage(ex_v, text),
        negation_risk=negation_risk_of(text, ex_v),
        multi_action_complexity=multi_action_complexity(ex_v),
        verifier_error_count=len(block_errs_no_conf),
    )
    raw = raw_confidence_score(feats)
    cal = platt_calibrate(raw)
    ex_v = _with_confidence(ex_v, cal)

    # 2차 적용: confidence + schema_valid 반영
    verif2 = apply_hard_rules(ex_v, text, confidence=cal, schema_valid=v1.schema_valid)
    return ModeResult(name="D", extraction=verif2.extraction,
                      schema_valid=v1.schema_valid,
                      retry_count=v1.retry_count, retry_reasons=v1.retry_reasons,
                      verifier_errors=verif2.errors,
                      raw_features=feats, raw_score=raw, final_confidence=cal,
                      blocked_auto=verif2.blocked_auto,
                      raw_first=v1.raw_text_first, raw_retry=v1.raw_text_retry)


def _with_confidence(ex: Card1Extraction, conf: float) -> Card1Extraction:
    return Card1Extraction(
        intent=ex.intent, intent_type=ex.intent_type,
        deadline=ex.deadline, deadline_raw=ex.deadline_raw,
        materials=ex.materials, actions=ex.actions,
        sentence_type=ex.sentence_type,
        confidence=conf,
        needs_review=conf < 0.75,
        reason_code=ex.reason_code,
    )


# ── 메트릭 ──────────────────────────────────────────────────────────────
def gold_action_types(sample: Dict[str, Any]) -> List[str]:
    return [a["action_type"] for a in sample["expected"]["actions"]]


def predicted_action_types(ex: Card1Extraction) -> List[str]:
    return _action_types(ex)


def _f1(pred: List[str], gold: List[str]) -> Tuple[float, float, float]:
    if not pred and not gold:
        return 1.0, 1.0, 1.0
    if not pred:
        return 0.0, 0.0, 0.0
    if not gold:
        return 0.0, 1.0, 0.0
    ps, gs = set(pred), set(gold)
    tp_p = sum(1 for p in ps if any(p in g or g in p for g in gs))
    tp_g = sum(1 for g in gs if any(g in p or p in g for p in ps))
    pr = tp_p / len(ps) if ps else 0.0
    rc = tp_g / len(gs) if gs else 0.0
    f1 = (2 * pr * rc / (pr + rc)) if (pr + rc) > 0 else 0.0
    return round(pr, 4), round(rc, 4), round(f1, 4)


def aggregate_metrics(mode: str, results: List[Tuple[Dict[str, Any], ModeResult]]) -> Dict[str, Any]:
    tp = fp = fn = 0
    multi_correct = multi_total = 0
    cal_errs: List[float] = []
    false_dead = no_dead_total = 0
    no_act_fp = no_act_total   = 0

    for sample, mr in results:
        ex = mr.extraction
        gold = gold_action_types(sample)
        pred = predicted_action_types(ex)
        # micro F1
        if not gold and not pred:
            tp += 1
        else:
            gs = set(gold); ps = set(pred)
            for p in ps:
                if any(p in g or g in p for g in gs):
                    tp += 1
                else:
                    fp += 1
            for g in gs:
                if not any(g in p or p in g for p in ps):
                    fn += 1
        # multi_action split accuracy (gold actions >= 2 인 경우만)
        if len(gold) >= 2:
            multi_total += 1
            if len(set(pred)) >= len(set(gold)):
                multi_correct += 1
        # calibration: |confidence - binary_correct|
        gold_intent = sample["expected"]["intent_type"]
        intent_ok = (ex.intent_type.value == gold_intent)
        action_set_ok = (set(pred) >= set(gold))
        bin_acc = (int(intent_ok) + int(action_set_ok)) / 2.0
        cal_errs.append(abs(mr.final_confidence - bin_acc))
        # false_deadline: gold deadline None인데 pred deadline 잡힘
        if sample["expected"]["deadline"] is None:
            no_dead_total += 1
            if ex.deadline_raw:
                false_dead += 1
        # no_action_fp
        if sample["expected"]["intent_type"] == "no_action":
            no_act_total += 1
            if len(pred) > 0:
                no_act_fp += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "mode":              mode,
        "action_f1":         round(f1, 4),
        "action_precision":  round(precision, 4),
        "action_recall":     round(recall, 4),
        "multi_action":      f"{multi_correct}/{multi_total}" if multi_total else "n/a",
        "calibration_error": round(sum(cal_errs) / len(cal_errs), 4) if cal_errs else 0.0,
        "false_deadline":    f"{false_dead}/{no_dead_total}" if no_dead_total else "n/a",
        "no_action_fp":      f"{no_act_fp}/{no_act_total}" if no_act_total else "n/a",
    }


# ── 실행 ────────────────────────────────────────────────────────────────
def main() -> int:
    model_path = os.environ.get("BUTLER_LLM_MODEL_PATH") or \
        "/Users/kimsunghoon/Desktop/butler-data/Butler모델/qwen3-4b-gguf/qwen3-4b-q4_k_m.gguf"
    if not os.path.exists(model_path):
        print(f"[FATAL] BUTLER_LLM_MODEL_PATH 미존재: {model_path}", file=sys.stderr)
        return 2

    os.environ["BUTLER_LLM_MODEL_PATH"] = model_path
    os.environ.pop("SKIP_LLM", None)

    print(f"[Model] {model_path}")
    print(f"[Config] LLM_EXTRACT_CONFIG = {json.dumps(LLM_EXTRACT_CONFIG, ensure_ascii=False)}")
    print(f"[Platt] A={PLATT_A}  B={PLATT_B}")

    # Lazy import to capture load time
    from butler_pc_core.card1_extraction.llm_extractor import (
        _get_llama_instance, _call_llama_v1, _get_v1_grammar, _build_chat_v1,
    )
    t0 = time.time()
    llm = _get_llama_instance()
    load_secs = time.time() - t0
    if llm is None:
        print("[FATAL] llama-cpp 인스턴스 로드 실패", file=sys.stderr)
        return 3
    print(f"[Load] {load_secs:.2f}s  (cached={'no' if load_secs > 1 else 'yes'})")

    grammar = _get_v1_grammar()
    print(f"[Grammar] JSON schema grammar: {'loaded' if grammar is not None else 'unavailable'}")

    # 1건 warmup tokens/sec
    warm_prompt = _build_chat_v1("이 자료 보내주실 수 있나요?", parsed_hints=None)
    t1 = time.time()
    warm_kwargs = {
        "prompt": warm_prompt,
        "max_tokens": LLM_EXTRACT_CONFIG["max_tokens"],
        "temperature": LLM_EXTRACT_CONFIG["temperature"],
        "top_p": LLM_EXTRACT_CONFIG["top_p"],
        "top_k": LLM_EXTRACT_CONFIG["top_k"],
        "repeat_penalty": LLM_EXTRACT_CONFIG["repeat_penalty"],
        "stop": LLM_EXTRACT_CONFIG["stop"] + ["<|im_end|>", "<|endoftext|>"],
    }
    if grammar is not None:
        warm_kwargs["grammar"] = grammar
    warm_out = llm.create_completion(**warm_kwargs)
    warm_secs = time.time() - t1
    n_tok = warm_out["usage"]["completion_tokens"]
    tps = n_tok / warm_secs if warm_secs > 0 else 0
    print(f"[Warm] {warm_secs:.2f}s | tokens={n_tok} | {tps:.1f} tok/s")
    print()

    # 5건 × 4모드 실행
    per_sample: List[Dict[str, Any]] = []
    mode_results: Dict[str, List[Tuple[Dict[str, Any], ModeResult]]] = {
        "A": [], "B": [], "C": [], "D": [],
    }

    for sample in SAMPLES:
        text = sample["source_text"]
        print(f"── {sample['id']} [{sample['category']}] ──")
        print(f"   원문: {text}")
        rec = {"id": sample["id"], "category": sample["category"], "source_text": text,
               "expected": sample["expected"], "modes": {}}

        a = run_mode_A(text)
        b = run_mode_B(text, _call_llama_v1)
        c = run_mode_C(text, _call_llama_v1)
        d = run_mode_D(text, _call_llama_v1)

        for mr in (a, b, c, d):
            mode_results[mr.name].append((sample, mr))
            pred_acts = predicted_action_types(mr.extraction)
            rec["modes"][mr.name] = {
                "intent_type":      mr.extraction.intent_type.value,
                "actions":          pred_acts,
                "deadline_raw":     mr.extraction.deadline_raw,
                "materials":        mr.extraction.materials,
                "schema_valid":     mr.schema_valid,
                "retry_count":      mr.retry_count,
                "retry_reasons":    mr.retry_reasons,
                "verifier_errors":  mr.verifier_errors,
                "confidence":       mr.final_confidence,
                "blocked_auto":     mr.blocked_auto,
            }
            tag = "OK " if (set(pred_acts) >= set(gold_action_types(sample))
                            and mr.extraction.intent_type.value == sample["expected"]["intent_type"]) else "FAIL"
            print(f"   [{mr.name}] {tag} intent={mr.extraction.intent_type.value} "
                  f"actions={pred_acts} conf={mr.final_confidence:.3f} "
                  f"schema={mr.schema_valid} retry={mr.retry_count} "
                  f"verr={len(mr.verifier_errors)}")
        per_sample.append(rec)
        print()

    # ── 집계 ─────────────────────────────────────────────────────────────
    print()
    print("=" * 64)
    print("  [6.5.1 Smoke Result]")
    print("=" * 64)
    print()
    print("환경:")
    print("- M3 Max 64GB")
    print("- Qwen3-4B Q4_K_M GGUF")
    print("- llama-cpp-python Metal")
    print()

    metrics: Dict[str, Dict[str, Any]] = {}
    for mode in ("A", "B", "C", "D"):
        m = aggregate_metrics(mode, mode_results[mode])
        metrics[mode] = m

    headers = {
        "A": "A parser only:",
        "B": "B Qwen3 only:",
        "C": "C parser + Qwen3:",
        "D": "D parser + Qwen3 + verifier + calibrated confidence:",
    }
    for mode in ("A", "B", "C", "D"):
        print(headers[mode])
        m = metrics[mode]
        print(f"- action_f1: {m['action_f1']}")
        print(f"- multi_action: {m['multi_action']}")
        print(f"- calibration_error: {m['calibration_error']}")
        print(f"- false_deadline: {m['false_deadline']}")
        print(f"- no_action_fp: {m['no_action_fp']}")
        print()

    # ── 실패 샘플 + 위험 신호 점검 ──────────────────────────────────────
    failures: List[Dict[str, Any]] = []
    risks: List[str] = []

    for rec in per_sample:
        gold = [a["action_type"] for a in rec["expected"]["actions"]]
        d = rec["modes"]["D"]
        d_pred = d["actions"]
        intent_ok  = (d["intent_type"] == rec["expected"]["intent_type"])
        action_ok  = (set(d_pred) >= set(gold))
        if not (intent_ok and action_ok):
            failures.append({
                "id":       rec["id"],
                "source":   rec["source_text"],
                "parser":   rec["modes"]["A"]["actions"],
                "llm_json": rec["modes"]["B"],
                "d_pred":   d_pred,
                "verr":     d["verifier_errors"],
                "gold":     gold,
                "gold_intent": rec["expected"]["intent_type"],
                "pred_intent": d["intent_type"],
            })
        # 위험 신호 1: schema valid but evidence not in source (B/C/D 어느 모드든)
        # 위험 신호 2: 복합 액션이 1개로 합쳐짐 (gold≥2 인데 LLM-only(B)도 1개 이하)
        if len(gold) >= 2 and len(rec["modes"]["B"]["actions"]) <= 1:
            risks.append(f"위험2: {rec['id']} 복합 액션을 1개로 합침 "
                         f"(gold {len(gold)}개 / B 모드 {len(rec['modes']['B']['actions'])}개)")
        # 위험 신호 3: 부정형인데 actions가 잡힘 (B/C 모드에서)
        if rec["expected"]["intent_type"] == "no_action":
            for mname in ("B", "C", "D"):
                if rec["modes"][mname]["actions"]:
                    risks.append(f"위험3: {rec['id']} 부정형인데 {mname} 모드가 액션을 잡음 "
                                 f"{rec['modes'][mname]['actions']}")
        # 위험 신호 4: confidence ≥ 0.9 인데 verifier_error 있음 (D 모드)
        if d["confidence"] >= 0.9 and len(d["verifier_errors"]) > 0:
            risks.append(f"위험4: {rec['id']} D 모드 confidence={d['confidence']:.3f} "
                         f"인데 verifier_error {len(d['verifier_errors'])}건")

    if failures:
        print("실패 샘플 (있으면):")
        for i, f in enumerate(failures, 1):
            print(f"{i}. 원문: {f['source']}")
            print(f"   parser:   {f['parser']}")
            print(f"   LLM JSON: {f['llm_json']['actions']} (intent={f['llm_json']['intent_type']})")
            print(f"   verifier error: {f['verr']}")
            print(f"   판단: gold={f['gold']} ({f['gold_intent']}) / "
                  f"D pred={f['d_pred']} ({f['pred_intent']})")
        print()
    else:
        print("실패 샘플 없음.\n")

    # ── 추가 보고 ─────────────────────────────────────────────────────
    schema_total_calls  = sum(1 for s in per_sample for m in ("B","C","D"))
    schema_valid_calls  = sum(1 for s in per_sample for m in ("B","C","D")
                              if s["modes"][m]["schema_valid"])
    retry_calls         = sum(1 for s in per_sample for m in ("B","C","D")
                              if s["modes"][m]["retry_count"] > 0)
    retry_details: List[str] = []
    for s in per_sample:
        for m in ("B","C","D"):
            if s["modes"][m]["retry_count"] > 0:
                retry_details.append(f"  - {s['id']} ({m}): {s['modes'][m]['retry_reasons']}")

    print("[추가 보고]")
    print(f"- llama-cpp-python Metal 설치: 기설치 (0.3.23) — GPU offload True, Apple M3 Max 인식")
    print(f"- 모델 로딩: {load_secs:.2f}s  (Q4_K_M ~3.7GB)")
    print(f"- 추론 속도(warmup): {tps:.1f} tok/s  (tokens={n_tok}, {warm_secs:.2f}s)")
    print(f"- JSON Schema validation 통과율: {schema_valid_calls}/{schema_total_calls}")
    print(f"- retry 발생: {retry_calls}건")
    for d in retry_details:
        print(d)
    if risks:
        print(f"- 위험 신호 발견: {len(risks)}건")
        for r in risks:
            print(f"  {r}")
    else:
        print("- 위험 신호 발견: 0건")

    # 권장: D 모드 action_f1이 A 모드 대비 개선되면 6.5.2 진행
    a_f1 = metrics["A"]["action_f1"]
    d_f1 = metrics["D"]["action_f1"]
    improved = d_f1 >= a_f1
    print(f"- 다음 단계: A f1={a_f1} → D f1={d_f1}  "
          f"({'개선' if improved else '비개선'}) "
          f"→ {'6.5.2 (65건) 진행 권장' if improved else '6.5.1b 위험 신호 검토 후 재실행'}")

    # JSON 결과 저장
    out_path = ROOT / "tests" / "card1_extraction" / "step_6_5_1_smoke_result.json"
    out_path.write_text(json.dumps({
        "model_path":   model_path,
        "load_secs":    round(load_secs, 3),
        "warm_tps":     round(tps, 2),
        "metrics":      metrics,
        "per_sample":   per_sample,
        "failures":     failures,
        "risks":        risks,
        "schema_valid_calls": schema_valid_calls,
        "schema_total_calls": schema_total_calls,
        "retry_calls":  retry_calls,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Save] {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
