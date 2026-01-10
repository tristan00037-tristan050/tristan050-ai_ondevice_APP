#!/usr/bin/env python3
"""
Effect Metrics: NDCG gain 및 causal proxy 지표 계산 (meta-only)
baseline vs variant 비교로 효과 지표 산출
"""

from typing import List, Tuple, Set
import math


def calculate_ndcg(ranked: List[Tuple[float, float, str, set]], relevant_docs: Set[str], k: int) -> float:
    """
    NDCG@K 계산
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (이미 정렬됨)
        relevant_docs: relevant document ID 집합 (문자열)
        k: topK 값
    
    Returns:
        NDCG@K 값 (0.0 ~ 1.0)
    """
    if not ranked or k <= 0:
        return 0.0
    
    # DCG 계산
    dcg = 0.0
    for idx, (_, _, did, _) in enumerate(ranked[:k], 1):
        if str(did) in relevant_docs:
            dcg += 1.0 / math.log2(idx + 1)
    
    # IDCG 계산 (ideal: 모든 relevant 문서가 상위에 위치)
    relevant_count = sum(1 for _, _, did, _ in ranked[:k] if str(did) in relevant_docs)
    ideal_hits = min(relevant_count, k)
    idcg = 0.0
    for idx in range(1, ideal_hits + 1):
        idcg += 1.0 / math.log2(idx + 1)
    
    return dcg / idcg if idcg > 0 else 0.0


def bucketize_ndcg(ndcg: float) -> str:
    """
    NDCG 값을 버킷으로 분류 (meta-only)
    
    Args:
        ndcg: NDCG 값 (0.0 ~ 1.0)
    
    Returns:
        버킷 문자열
    """
    if ndcg >= 0.9:
        return "EXCELLENT"
    elif ndcg >= 0.7:
        return "GOOD"
    elif ndcg >= 0.5:
        return "FAIR"
    elif ndcg >= 0.3:
        return "POOR"
    else:
        return "VERY_POOR"


def bucketize_ndcg_gain(gain: float) -> str:
    """
    NDCG gain 값을 버킷으로 분류 (meta-only)
    
    Args:
        gain: NDCG gain 값 (variant - baseline)
    
    Returns:
        버킷 문자열
    """
    if gain >= 0.1:
        return "LARGE_GAIN"
    elif gain >= 0.05:
        return "MEDIUM_GAIN"
    elif gain >= 0.01:
        return "SMALL_GAIN"
    elif gain >= -0.01:
        return "NEUTRAL"
    elif gain >= -0.05:
        return "SMALL_LOSS"
    elif gain >= -0.1:
        return "MEDIUM_LOSS"
    else:
        return "LARGE_LOSS"


def calculate_ips_bucket(
    baseline_ranked: List[str],
    variant_ranked: List[str],
    relevant_docs: Set[str],
    k: int
) -> str:
    """
    Inverse Propensity Scoring (IPS) bucket 계산 (최소형 causal proxy)
    
    IPS는 propensity (노출 확률)의 역수를 가중치로 사용하여 unbiased 추정을 수행합니다.
    여기서는 간단한 휴리스틱으로 propensity를 추정합니다.
    
    Args:
        baseline_ranked: baseline 랭킹 (doc_id 리스트)
        variant_ranked: variant 랭킹 (doc_id 리스트)
        relevant_docs: relevant document ID 집합
        k: topK 값
    
    Returns:
        IPS gain bucket (meta-only)
    """
    if not baseline_ranked or not variant_ranked or k <= 0:
        return "UNKNOWN"
    
    # Baseline propensity: 1/rank (상위일수록 높은 propensity)
    baseline_propensity_sum = 0.0
    baseline_relevant_count = 0
    for idx, did in enumerate(baseline_ranked[:k], 1):
        propensity = 1.0 / idx  # 간단한 휴리스틱
        baseline_propensity_sum += propensity
        if str(did) in relevant_docs:
            baseline_relevant_count += 1
    
    # Variant propensity
    variant_propensity_sum = 0.0
    variant_relevant_count = 0
    for idx, did in enumerate(variant_ranked[:k], 1):
        propensity = 1.0 / idx
        variant_propensity_sum += propensity
        if str(did) in relevant_docs:
            variant_relevant_count += 1
    
    # IPS gain (간단한 휴리스틱)
    # 실제 IPS는 더 복잡하지만, 여기서는 propensity 기반 차이를 버킷으로 분류
    if baseline_propensity_sum == 0:
        return "UNKNOWN"
    
    ips_ratio = variant_propensity_sum / baseline_propensity_sum if baseline_propensity_sum > 0 else 1.0
    ips_gain = ips_ratio - 1.0
    
    # 버킷화
    if ips_gain >= 0.1:
        return "LARGE_IPS_GAIN"
    elif ips_gain >= 0.05:
        return "MEDIUM_IPS_GAIN"
    elif ips_gain >= 0.01:
        return "SMALL_IPS_GAIN"
    elif ips_gain >= -0.01:
        return "NEUTRAL_IPS"
    elif ips_gain >= -0.05:
        return "SMALL_IPS_LOSS"
    elif ips_gain >= -0.1:
        return "MEDIUM_IPS_LOSS"
    else:
        return "LARGE_IPS_LOSS"


def calculate_effect_metrics(
    baseline_ranked: List[Tuple[float, float, str, set]],
    variant_ranked: List[Tuple[float, float, str, set]],
    relevant_docs: Set[str],
    k: int
) -> dict:
    """
    효과 지표 계산 (meta-only)
    
    Args:
        baseline_ranked: baseline 랭킹 [(primary, secondary, did, dt), ...]
        variant_ranked: variant 랭킹 [(primary, secondary, did, dt), ...]
        relevant_docs: relevant document ID 집합
        k: topK 값
    
    Returns:
        meta-only 효과 지표 딕셔너리
    """
    # Baseline NDCG
    ndcg_baseline = calculate_ndcg(baseline_ranked, relevant_docs, k)
    
    # Variant NDCG
    ndcg_variant = calculate_ndcg(variant_ranked, relevant_docs, k)
    
    # NDCG gain
    ndcg_gain = ndcg_variant - ndcg_baseline
    
    # Baseline doc_id 리스트 (IPS 계산용)
    baseline_did_list = [did for _, _, did, _ in baseline_ranked[:k]]
    variant_did_list = [did for _, _, did, _ in variant_ranked[:k]]
    
    # IPS bucket (선택)
    ips_bucket = calculate_ips_bucket(baseline_did_list, variant_did_list, relevant_docs, k)
    
    return {
        "ndcg_at_k_baseline_bucket": bucketize_ndcg(ndcg_baseline),
        "ndcg_at_k_variant_bucket": bucketize_ndcg(ndcg_variant),
        "ndcg_at_k_gain_bucket": bucketize_ndcg_gain(ndcg_gain),
        "ips_gain_bucket": ips_bucket,
    }


if __name__ == "__main__":
    # Unit test용
    # Test 1: NDCG 계산 검증
    ranked_test = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs_test = {"doc1", "doc2"}
    ndcg = calculate_ndcg(ranked_test, relevant_docs_test, 3)
    assert 0.0 <= ndcg <= 1.0, f"NDCG out of range: {ndcg}"
    print("PASS: NDCG calculation")
    
    # Test 2: Bucketization 검증
    assert bucketize_ndcg(0.95) == "EXCELLENT"
    assert bucketize_ndcg_gain(0.15) == "LARGE_GAIN"
    assert bucketize_ndcg_gain(-0.15) == "LARGE_LOSS"
    print("PASS: bucketization")
    
    # Test 3: Effect metrics meta-only 검증
    baseline_test = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    variant_test = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    metrics = calculate_effect_metrics(baseline_test, variant_test, relevant_docs_test, 3)
    
    assert "ndcg_at_k_baseline_bucket" in metrics
    assert "ndcg_at_k_variant_bucket" in metrics
    assert "ndcg_at_k_gain_bucket" in metrics
    assert "ips_gain_bucket" in metrics
    
    # Meta-only 검증 (문자열만)
    allowed_types = (str,)
    for key, value in metrics.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
    
    # 원문/후보 리스트 출력 없음 확인
    assert "ranked" not in metrics
    assert "docs" not in metrics
    assert "query" not in metrics
    
    print("PASS: effect metrics meta-only")
    print("OK: Effect metrics tests passed")

