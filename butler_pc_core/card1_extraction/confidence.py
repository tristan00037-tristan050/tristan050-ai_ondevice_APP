"""confidence.py — evidence 기반 신뢰도 산출 (알고리즘 팀 §6-6).

- ConfidenceFactors / compute_card1_confidence: 단계 6.3~6.4 기준선 (heuristic Platt-linear).
- ConfidenceFeatures / raw_confidence_score / platt_calibrate: 단계 6.5.1 알고리즘 팀 §6 신규.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ConfidenceFactors:
    action_verb_count:  int   = 0     # ACTION_VERBS 원문 히트 수
    deadline_found:     bool  = False  # DEADLINE_PATTERNS 원문 매칭 여부
    deadline_claimed:   bool  = False  # 마감 주장 여부 (LLM/파서 출력)
    material_count:     int   = 0     # 원문 근거 있는 자료 수
    action_count:       int   = 0     # 원문 근거 있는 액션 수
    hallucination_count: int  = 0     # 원문 근거 없는 항목 수 (verifier 판정)


_BASE_SCORE = 0.35


def compute_card1_confidence(factors: ConfidenceFactors) -> float:
    """
    evidence 기반 신뢰도 계산 (Platt-style 보정 적용).

    구성:
      base                          = 0.35  (heuristic calibration 보정)
      의도 근거 (ACTION_VERBS 히트)   → +0.20  (0.25 → 0.20 하향)
      마감 근거 (DEADLINE_PATTERNS)   → +0.20 (근거 없이 주장 시 -0.15)
      자료 근거                       → +0.05 × hits (max 0.15)
      액션 근거                       → +0.05 × hits (max 0.15)
      hallucination penalty          → -0.15 × count

    Platt-style calibration: raw → calibrated = 0.85 × raw + 0.05
    heuristic 예상 정확도 ~75-85% 구간 → 신뢰도 0.60~0.75 수렴.

    구간 (§6-6):
      0.90+     : 자동 적용
      0.75~0.89 : 확인 배지
      0.60~0.74 : 사용자 확인 필요
      0.60 미만  : 자동 적용 X
    """
    score = _BASE_SCORE

    if factors.action_verb_count > 0:
        score += 0.20

    if factors.deadline_found:
        score += 0.20
    elif factors.deadline_claimed:
        score -= 0.15

    score += min(factors.material_count * 0.05, 0.15)
    score += min(factors.action_count   * 0.05, 0.15)
    score -= factors.hallucination_count * 0.15

    raw = max(0.0, min(1.0, score))

    # Platt-style linear calibration (heuristic 과신뢰 억제)
    calibrated = 0.85 * raw + 0.05

    return round(max(0.0, min(1.0, calibrated)), 3)


def confidence_band(confidence: float) -> str:
    """신뢰도 수치 → 구간 레이블."""
    if confidence >= 0.90:
        return "auto"
    if confidence >= 0.75:
        return "badge"
    if confidence >= 0.60:
        return "confirm"
    return "blocked"


# ── 단계 6.5.1 — 알고리즘 팀 §6 신규 ConfidenceFeatures ───────────────────────

# Platt sigmoid 초기값 — 평가셋 50~80건 결과로 fit 후 갱신 (6.5.2/6.5.3)
PLATT_A: float = -4.0
PLATT_B: float =  2.0

# 가중치 (알고리즘 팀 §6 — 절대 준수)
W_PARSER_INTENT:        float =  0.15
W_PARSER_DEADLINE:      float =  0.10
W_PARSER_MATERIAL:      float =  0.10
W_PARSER_ACTION:        float =  0.15
W_LLM_SCHEMA_VALID:     float =  0.15
W_LLM_PARSER_AGREEMENT: float =  0.15
W_EVIDENCE_COVERAGE:    float =  0.20
W_NEGATION_RISK:        float = -0.15
W_MULTI_ACTION_PENALTY: float = -0.05
W_VERIFIER_ERROR:       float = -0.20


@dataclass
class ConfidenceFeatures:
    """알고리즘 팀 §6 — confidence 산출 입력 특성 (LLM 자기평가 금지)."""

    parser_intent_score:     float = 0.0   # parser intent 신뢰도 [0,1]
    parser_deadline_score:   float = 0.0   # parser deadline 신뢰도 [0,1]
    parser_material_score:   float = 0.0   # parser material 신뢰도 [0,1]
    parser_action_score:     float = 0.0   # parser action 신뢰도 [0,1]

    llm_schema_valid:        bool  = False  # JSON Schema validation 통과
    llm_parser_agreement:    float = 0.0   # LLM/parser 액션 IoU [0,1]
    evidence_coverage:       float = 0.0   # action evidence 원문 매칭률 [0,1]

    negation_risk:           float = 0.0   # 부정형 위험 [0,1]
    multi_action_complexity: float = 0.0   # 액션 ≥3 = 1.0 / 2 = 0.5 / 1 = 0.0
    verifier_error_count:    int   = 0     # verifier hard rule 위반 수


def raw_confidence_score(features: ConfidenceFeatures) -> float:
    """알고리즘 팀 §6 — 가중합 (Platt sigmoid 전 raw, 음수 가능)."""
    score  = features.parser_intent_score     * W_PARSER_INTENT
    score += features.parser_deadline_score   * W_PARSER_DEADLINE
    score += features.parser_material_score   * W_PARSER_MATERIAL
    score += features.parser_action_score     * W_PARSER_ACTION
    score += (1.0 if features.llm_schema_valid else 0.0) * W_LLM_SCHEMA_VALID
    score += features.llm_parser_agreement    * W_LLM_PARSER_AGREEMENT
    score += features.evidence_coverage       * W_EVIDENCE_COVERAGE
    score += features.negation_risk           * W_NEGATION_RISK         # 음수 가중
    score += features.multi_action_complexity * W_MULTI_ACTION_PENALTY  # 음수 가중
    score += features.verifier_error_count    * W_VERIFIER_ERROR        # 음수 가중
    return round(score, 4)


def platt_calibrate(raw: float, a: float = PLATT_A, b: float = PLATT_B) -> float:
    """Platt sigmoid: 1 / (1 + exp(A*raw + B)) → [0,1]."""
    try:
        z = a * raw + b
        if z > 35:
            return 0.0
        if z < -35:
            return 1.0
        return round(1.0 / (1.0 + math.exp(z)), 4)
    except OverflowError:
        return 0.0 if (a * raw + b) > 0 else 1.0


def calibrated_confidence(features: ConfidenceFeatures) -> float:
    """ConfidenceFeatures → Platt 보정 confidence."""
    return platt_calibrate(raw_confidence_score(features))


# ─────────────────────────────────────────────────────────────────────────
# 단계 6.5.3 Patch 4 — calibration target 분리 (action/intent/overall)
# ─────────────────────────────────────────────────────────────────────────

# action target — normalized_action 정답 AND evidence OK AND no verifier action error
# intent target — intent 정답 AND normalizer conflict 없음
# overall target — action AND intent AND deadline/material OK
#
# final_confidence = min(action_conf, intent_conf, deadline_conf, material_conf)


def action_raw_score(features: ConfidenceFeatures, multi_action_count: int = 0,
                     all_actions_have_evidence: bool = True) -> float:
    """action 정답 가능성 raw score [-,+].

    multi_action 보너스/패널티:
      - count > 1 AND 모든 evidence OK → +0.05 (보상)
      - 그 외 → -0.05 × multi_action_complexity (패널티)
    """
    s  = features.parser_action_score   * 0.25
    s += features.parser_material_score * 0.10
    s += (1.0 if features.llm_schema_valid else 0.0) * 0.20
    s += features.llm_parser_agreement              * 0.20
    s += features.evidence_coverage                 * 0.30
    s -= features.verifier_error_count              * 0.20
    s -= features.negation_risk                     * 0.10

    if multi_action_count > 1 and all_actions_have_evidence:
        s += 0.05
    else:
        s -= 0.05 * features.multi_action_complexity
    return round(s, 4)


def intent_raw_score(features: ConfidenceFeatures,
                     normalizer_applied: bool = False,
                     normalizer_conflict: bool = False) -> float:
    """intent 정답 가능성 raw score.

    normalizer_applied=True 면 +0.10 (정확한 신호 발견).
    normalizer_conflict=True 면 -0.20 (REPORT+REQUEST 동시 출현 등).
    """
    s  = features.parser_intent_score   * 0.40
    s += features.evidence_coverage     * 0.20
    s += (1.0 if features.llm_schema_valid else 0.0) * 0.20
    if normalizer_applied:
        s += 0.10
    if normalizer_conflict:
        s -= 0.20
    return round(s, 4)


def overall_raw_score(features: ConfidenceFeatures,
                      deadline_ok: bool = True, material_ok: bool = True) -> float:
    """전체 정답 가능성 — parser features + LLM + verifier 종합."""
    s  = features.parser_intent_score     * 0.15
    s += features.parser_deadline_score   * 0.10
    s += features.parser_material_score   * 0.10
    s += features.parser_action_score     * 0.15
    s += (1.0 if features.llm_schema_valid else 0.0) * 0.15
    s += features.llm_parser_agreement    * 0.15
    s += features.evidence_coverage       * 0.20
    s -= features.negation_risk           * 0.15
    s -= features.multi_action_complexity * 0.05
    s -= features.verifier_error_count    * 0.20
    if not deadline_ok:
        s -= 0.15
    if not material_ok:
        s -= 0.10
    return round(s, 4)


def deadline_confidence_heuristic(features: ConfidenceFeatures,
                                  block_7_fired: bool = False) -> float:
    """deadline component confidence [0,1] (Platt fit 대상 아님)."""
    if block_7_fired:
        return 0.30
    return round(max(0.30, 0.50 + 0.50 * features.parser_deadline_score), 4)


def material_confidence_heuristic(features: ConfidenceFeatures,
                                  block_2_fired: bool = False) -> float:
    if block_2_fired:
        return 0.40
    return round(max(0.40, 0.50 + 0.50 * features.parser_material_score), 4)


def compose_final_confidence(action_conf: float, intent_conf: float,
                             deadline_conf: float, material_conf: float) -> float:
    """알고리즘 팀 §6.5.3 — final = min(4 component) — 단계 6.5.4에서 폐기.

    단계 6.5.4 부터는 weighted_final_confidence + hard_gates 사용.
    호환을 위해 유지 (테스트 의존성).
    """
    return round(min(action_conf, intent_conf, deadline_conf, material_conf), 4)


# ─────────────────────────────────────────────────────────────────────────
# 단계 6.5.4 Patch D — absent-field skip + hard gate + weighted aggregation
# ─────────────────────────────────────────────────────────────────────────

# auto_apply 임계값 (알고리즘 팀 §6.5.4)
AUTO_APPLY_THRESHOLDS = {
    "action":         0.85,
    "intent":         0.75,
    "deadline":       0.85,
    "material":       0.75,
    "final_weighted": 0.80,
}

# weighted aggregation 가중치 (deadline/material absent 시 normalize)
COMPONENT_WEIGHTS = {
    "action":   0.45,
    "intent":   0.30,
    "material": 0.15,
    "deadline": 0.10,
}


def aggregate_confidence(components: dict, present_fields: set) -> float:
    """absent field skip min — required(action/intent) + 있는 것만(deadline/material).

    Returns 0.0 if no values to aggregate.
    """
    active = ["action", "intent"]
    if "deadline" in present_fields: active.append("deadline")
    if "material" in present_fields: active.append("material")
    values = [components[k] for k in active if k in components]
    if not values:
        return 0.0
    return round(min(values), 4)


def weighted_final_confidence(
    components:     dict,
    present_fields: set,
    gates:          dict,
) -> float:
    """알고리즘 팀 §6.5.4 — hard gate 통과 후 weighted average.

    gates: {"schema_ok": bool, "verifier_ok": bool, "evidence_ok": bool}
    Returns 0.0 if any hard gate fails.
    """
    if not gates.get("schema_ok", False):    return 0.0
    if not gates.get("verifier_ok", False):  return 0.0
    if not gates.get("evidence_ok", False):  return 0.0

    total, denom = 0.0, 0.0
    for k, w in COMPONENT_WEIGHTS.items():
        if k in {"deadline", "material"} and k not in present_fields:
            continue
        if k not in components:
            continue
        total += components[k] * w
        denom += w
    return round(total / denom if denom > 0 else 0.0, 4)


def should_auto_apply(
    components:     dict,
    present_fields: set,
    final_weighted: float,
    gates:          dict,
) -> tuple[bool, str]:
    """알고리즘 팀 §6.5.4 — auto_apply 5중 임계 통과 여부.

    Returns:
        (auto_ok, reason)
        reason: "OK" 또는 어느 임계에서 막혔는지
    """
    if not gates.get("schema_ok", False):    return False, "schema_gate"
    if not gates.get("verifier_ok", False):  return False, "verifier_gate"
    if not gates.get("evidence_ok", False):  return False, "evidence_gate"

    if components.get("action", 0.0) < AUTO_APPLY_THRESHOLDS["action"]:
        return False, "action_below_threshold"
    if components.get("intent", 0.0) < AUTO_APPLY_THRESHOLDS["intent"]:
        return False, "intent_below_threshold"
    if "deadline" in present_fields and \
       components.get("deadline", 0.0) < AUTO_APPLY_THRESHOLDS["deadline"]:
        return False, "deadline_below_threshold"
    if "material" in present_fields and \
       components.get("material", 0.0) < AUTO_APPLY_THRESHOLDS["material"]:
        return False, "material_below_threshold"
    if final_weighted < AUTO_APPLY_THRESHOLDS["final_weighted"]:
        return False, "final_below_threshold"

    return True, "OK"
