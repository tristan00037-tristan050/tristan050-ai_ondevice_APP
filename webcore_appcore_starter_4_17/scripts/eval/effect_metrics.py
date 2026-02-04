#!/usr/bin/env python3
"""
Effect Metrics: NDCG gain 및 causal proxy 지표 계산 (meta-only, fail-closed)
- NDCG@K gain (treatment vs baseline)
- Off-policy estimators: IPS and SNIPS (when propensities are available)
All outputs must be meta-only aggregates.
"""

from typing import List, Tuple, Set, Optional, Dict, Any
import math


def calculate_ndcg_at_k(
    ranked: List[Tuple[float, float, str, set]],
    relevance_labels: Dict[str, float],
    k: int
) -> Optional[float]:
    """
    NDCG@K 계산 (graded relevance labels 사용)
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (이미 정렬됨)
        relevance_labels: {doc_id: relevance_score, ...} 딕셔너리 (0.0 ~ 1.0 또는 정수)
        k: topK 값
    
    Returns:
        NDCG@K 값 (0.0 ~ 1.0) 또는 None (fail-closed)
    """
    if not ranked or k <= 0:
        return None
    
    # DCG 계산
    dcg = 0.0
    for idx, (_, _, did, _) in enumerate(ranked[:k], 1):
        doc_id = str(did)
        relevance = relevance_labels.get(doc_id, 0.0)
        
        # Fail-Closed: NaN/inf 체크
        if not isinstance(relevance, (int, float)) or math.isnan(relevance) or math.isinf(relevance):
            return None
        
        dcg += relevance / math.log2(idx + 1)
    
    # IDCG 계산 (ideal: 모든 relevant 문서가 상위에 위치)
    sorted_relevances = sorted([v for v in relevance_labels.values() if isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v)], reverse=True)
    ideal_hits = min(len(sorted_relevances), k)
    idcg = 0.0
    for idx in range(1, ideal_hits + 1):
        if idx <= len(sorted_relevances):
            idcg += sorted_relevances[idx - 1] / math.log2(idx + 1)
    
    # Fail-Closed: denom=0 체크
    if idcg == 0.0:
        return None
    
    ndcg = dcg / idcg
    
    # Fail-Closed: 결과가 NaN/inf인지 체크
    if math.isnan(ndcg) or math.isinf(ndcg):
        return None
    
    return ndcg


def calculate_ips(
    logged_propensities: Dict[str, float],
    observed_rewards: Dict[str, float],
    treatment_ranked: List[str]
) -> Optional[float]:
    """
    Inverse Propensity Scoring (IPS) 계산
    
    Args:
        logged_propensities: {doc_id: p(a|x), ...} 딕셔너리 (propensity)
        observed_rewards: {doc_id: r, ...} 딕셔너리 (observed reward)
        treatment_ranked: treatment 랭킹 (doc_id 리스트)
    
    Returns:
        IPS 값 또는 None (fail-closed)
    """
    if not treatment_ranked:
        return None
    
    ips_sum = 0.0
    count = 0
    
    for doc_id in treatment_ranked:
        doc_id_str = str(doc_id)
        propensity = logged_propensities.get(doc_id_str)
        reward = observed_rewards.get(doc_id_str, 0.0)
        
        # Fail-Closed: propensity missing
        if propensity is None:
            return None
        
        # Fail-Closed: NaN/inf 체크
        if not isinstance(propensity, (int, float)) or math.isnan(propensity) or math.isinf(propensity):
            return None
        if not isinstance(reward, (int, float)) or math.isnan(reward) or math.isinf(reward):
            return None
        
        # Fail-Closed: denom=0 체크
        if propensity == 0.0:
            return None
        
        ips_sum += reward / propensity
        count += 1
    
    if count == 0:
        return None
    
    ips = ips_sum / count
    
    # Fail-Closed: 결과가 NaN/inf인지 체크
    if math.isnan(ips) or math.isinf(ips):
        return None
    
    return ips


def calculate_snips(
    logged_propensities: Dict[str, float],
    observed_rewards: Dict[str, float],
    treatment_ranked: List[str]
) -> Optional[float]:
    """
    Self-Normalized Inverse Propensity Scoring (SNIPS) 계산
    
    Args:
        logged_propensities: {doc_id: p(a|x), ...} 딕셔너리 (propensity)
        observed_rewards: {doc_id: r, ...} 딕셔너리 (observed reward)
        treatment_ranked: treatment 랭킹 (doc_id 리스트)
    
    Returns:
        SNIPS 값 또는 None (fail-closed)
    """
    if not treatment_ranked:
        return None
    
    numerator_sum = 0.0
    denominator_sum = 0.0
    count = 0
    
    for doc_id in treatment_ranked:
        doc_id_str = str(doc_id)
        propensity = logged_propensities.get(doc_id_str)
        reward = observed_rewards.get(doc_id_str, 0.0)
        
        # Fail-Closed: propensity missing
        if propensity is None:
            return None
        
        # Fail-Closed: NaN/inf 체크
        if not isinstance(propensity, (int, float)) or math.isnan(propensity) or math.isinf(propensity):
            return None
        if not isinstance(reward, (int, float)) or math.isnan(reward) or math.isinf(reward):
            return None
        
        # Fail-Closed: denom=0 체크
        if propensity == 0.0:
            return None
        
        numerator_sum += reward / propensity
        denominator_sum += 1.0 / propensity
        count += 1
    
    if count == 0:
        return None
    
    # Fail-Closed: denominator_sum=0 체크
    if denominator_sum == 0.0:
        return None
    
    snips = numerator_sum / denominator_sum
    
    # Fail-Closed: 결과가 NaN/inf인지 체크
    if math.isnan(snips) or math.isinf(snips):
        return None
    
    return snips


def calculate_effect_metrics(
    baseline_ranked: List[Tuple[float, float, str, set]],
    treatment_ranked: List[Tuple[float, float, str, set]],
    relevance_labels: Optional[Dict[str, float]],
    k: int = 10,
    logged_propensities: Optional[Dict[str, float]] = None,
    observed_rewards: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    효과 지표 계산 (meta-only, fail-closed)
    
    Args:
        baseline_ranked: baseline 랭킹 [(primary, secondary, did, dt), ...]
        treatment_ranked: treatment 랭킹 [(primary, secondary, did, dt), ...]
        relevance_labels: {doc_id: relevance_score, ...} 딕셔너리 (graded relevance)
        k: topK 값 (기본값: 10)
        logged_propensities: {doc_id: p(a|x), ...} 딕셔너리 (optional)
        observed_rewards: {doc_id: r, ...} 딕셔너리 (optional)
    
    Returns:
        meta-only 효과 지표 딕셔너리 (fail-closed)
    """
    result: Dict[str, Any] = {
        "effect_ndcg_at_10_baseline": None,
        "effect_ndcg_at_10_treatment": None,
        "effect_ndcg_gain_at_10": None,
        "effect_ips": None,
        "effect_snips": None,
        "effect_reason_code": "EFFECT_OK",
    }
    
    # NDCG@K 계산
    if relevance_labels is None:
        result["effect_reason_code"] = "EFFECT_LABELS_MISSING"
        return result
    
    # Baseline NDCG
    ndcg_baseline = calculate_ndcg_at_k(baseline_ranked, relevance_labels, k)
    if ndcg_baseline is None:
        result["effect_reason_code"] = "EFFECT_NUMERIC_INVALID"
        return result
    
    # Treatment NDCG
    ndcg_treatment = calculate_ndcg_at_k(treatment_ranked, relevance_labels, k)
    if ndcg_treatment is None:
        result["effect_reason_code"] = "EFFECT_NUMERIC_INVALID"
        return result
    
    # NDCG gain
    ndcg_gain = ndcg_treatment - ndcg_baseline
    
    # Fail-Closed: gain이 NaN/inf인지 체크
    if math.isnan(ndcg_gain) or math.isinf(ndcg_gain):
        result["effect_reason_code"] = "EFFECT_NUMERIC_INVALID"
        return result
    
    result["effect_ndcg_at_10_baseline"] = round(ndcg_baseline, 6)
    result["effect_ndcg_at_10_treatment"] = round(ndcg_treatment, 6)
    result["effect_ndcg_gain_at_10"] = round(ndcg_gain, 6)
    
    # IPS/SNIPS 계산 (propensities가 있을 때만)
    if logged_propensities is None or observed_rewards is None:
        result["effect_reason_code"] = "EFFECT_PROPENSITY_MISSING"
        return result
    
    # Treatment doc_id 리스트
    treatment_did_list = [str(did) for _, _, did, _ in treatment_ranked[:k]]
    
    # IPS 계산
    ips = calculate_ips(logged_propensities, observed_rewards, treatment_did_list)
    if ips is None:
        result["effect_reason_code"] = "EFFECT_PROPENSITY_MISSING"
        return result
    
    result["effect_ips"] = round(ips, 6)
    
    # SNIPS 계산
    snips = calculate_snips(logged_propensities, observed_rewards, treatment_did_list)
    if snips is None:
        result["effect_reason_code"] = "EFFECT_PROPENSITY_MISSING"
        return result
    
    result["effect_snips"] = round(snips, 6)
    
    return result


if __name__ == "__main__":
    # Unit test용
    print("OK: Effect metrics module loaded")

