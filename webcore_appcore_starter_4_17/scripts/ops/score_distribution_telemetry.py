#!/usr/bin/env python3
"""
Score Distribution Telemetry (Shadow only, meta-only)
topK 후보의 primary score 및 gap 분포에 대한 meta-only 지표 산출
랭킹/결과는 절대 바꾸지 않음 (Shadow only)
"""

import json
import math
from typing import List, Tuple


def percentile(data: List[float], p: float) -> float:
    """Percentile 계산 (결정론적)"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


def calculate_gaps(scores: List[float]) -> List[float]:
    """인접 score 간 gap 계산 (내림차순 가정)"""
    if len(scores) < 2:
        return []
    gaps = []
    for i in range(len(scores) - 1):
        gap = scores[i] - scores[i + 1]
        gaps.append(gap)
    return gaps


def calculate_entropy(scores: List[float]) -> float:
    """정규화 엔트로피 계산 (결정론적)"""
    if not scores or len(scores) == 0:
        return 0.0
    
    # Score를 양수로 정규화 (min을 0으로)
    min_score = min(scores)
    if min_score < 0:
        normalized = [s - min_score for s in scores]
    else:
        normalized = scores
    
    # 합이 0이면 엔트로피 0
    total = sum(normalized)
    if total == 0:
        return 0.0
    
    # 확률 분포로 정규화
    probs = [s / total for s in normalized]
    
    # 엔트로피 계산: -sum(p * log2(p))
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log2(p)
    
    # 정규화: log2(n)으로 나눔
    n = len(scores)
    if n <= 1:
        return 0.0
    normalized_entropy = entropy / math.log2(n)
    
    return normalized_entropy


def calculate_gini(scores: List[float]) -> float:
    """지니 계수 계산 (결정론적)"""
    if not scores or len(scores) < 2:
        return 0.0
    
    # Score를 양수로 정규화
    min_score = min(scores)
    if min_score < 0:
        normalized = [s - min_score + 1.0 for s in scores]  # +1 to ensure positive
    else:
        normalized = [s + 1.0 for s in scores]  # +1 to ensure positive
    
    # 정렬 (오름차순)
    sorted_scores = sorted(normalized)
    n = len(sorted_scores)
    total = sum(sorted_scores)
    
    if total == 0:
        return 0.0
    
    # 지니 계수: 1 - 2 * sum((n - i + 0.5) * score[i]) / (n * sum(scores))
    cumsum = 0.0
    for i, score in enumerate(sorted_scores):
        cumsum += (n - i + 0.5) * score
    
    gini = 1.0 - (2.0 * cumsum) / (n * total)
    return max(0.0, min(1.0, gini))  # 0~1 범위로 클램핑


def bucketize_entropy(entropy: float) -> str:
    """엔트로피 버킷화 (meta-only)"""
    if entropy < 0.2:
        return "VERY_LOW"
    elif entropy < 0.4:
        return "LOW"
    elif entropy < 0.6:
        return "MEDIUM"
    elif entropy < 0.8:
        return "HIGH"
    else:
        return "VERY_HIGH"


def bucketize_gini(gini: float) -> str:
    """지니 계수 버킷화 (meta-only)"""
    if gini < 0.2:
        return "LOW_INEQUALITY"
    elif gini < 0.4:
        return "MEDIUM_INEQUALITY"
    elif gini < 0.6:
        return "HIGH_INEQUALITY"
    else:
        return "VERY_HIGH_INEQUALITY"


def bucketize_unique_count(count: int, topk: int) -> str:
    """고유 score 개수 버킷화 (meta-only)"""
    ratio = count / topk if topk > 0 else 0.0
    if ratio < 0.3:
        return "LOW_DIVERSITY"
    elif ratio < 0.6:
        return "MEDIUM_DIVERSITY"
    else:
        return "HIGH_DIVERSITY"


def calculate_distribution_telemetry(ranked: List[Tuple[float, float, str, set]], topk: int) -> dict:
    """
    분포 텔레메트리 계산 (Shadow only, meta-only)
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (이미 정렬됨)
        topk: topK 값
    
    Returns:
        meta-only 지표 딕셔너리
    """
    if not ranked or len(ranked) == 0:
        return {
            "gap_p25": 0.0,
            "gap_p50": 0.0,
            "gap_p75": 0.0,
            "score_entropy_bucket": "VERY_LOW",
            "score_gini_bucket": "LOW_INEQUALITY",
            "unique_score_count_bucket": "LOW_DIVERSITY",
        }
    
    # topK만 사용
    topk_ranked = ranked[:topk]
    
    # Primary score 추출
    primary_scores = [p for p, _, _, _ in topk_ranked]
    
    # Gap 계산
    gaps = calculate_gaps(primary_scores)
    
    # Gap percentiles
    gap_p25 = percentile(gaps, 0.25) if gaps else 0.0
    gap_p50 = percentile(gaps, 0.50) if gaps else 0.0
    gap_p75 = percentile(gaps, 0.75) if gaps else 0.0
    
    # 엔트로피 계산 및 버킷화
    entropy = calculate_entropy(primary_scores)
    entropy_bucket = bucketize_entropy(entropy)
    
    # 지니 계수 계산 및 버킷화
    gini = calculate_gini(primary_scores)
    gini_bucket = bucketize_gini(gini)
    
    # 고유 score 개수
    unique_scores = len(set(primary_scores))
    unique_count_bucket = bucketize_unique_count(unique_scores, len(topk_ranked))
    
    return {
        "gap_p25": round(gap_p25, 6),
        "gap_p50": round(gap_p50, 6),
        "gap_p75": round(gap_p75, 6),
        "score_entropy_bucket": entropy_bucket,
        "score_gini_bucket": gini_bucket,
        "unique_score_count_bucket": unique_count_bucket,
    }


if __name__ == "__main__":
    # Unit test용
    import sys
    
    # Test 1: 결정론적 엔트로피
    test_scores1 = [5.0, 4.0, 3.0, 2.0, 1.0]
    entropy1 = calculate_entropy(test_scores1)
    print(f"Test 1 - Entropy: {entropy1:.6f}")
    
    # Test 2: 결정론적 지니
    gini1 = calculate_gini(test_scores1)
    print(f"Test 2 - Gini: {gini1:.6f}")
    
    # Test 3: 동일 입력에 대한 재현성
    entropy2 = calculate_entropy(test_scores1)
    gini2 = calculate_gini(test_scores1)
    assert abs(entropy1 - entropy2) < 1e-10, "Entropy not deterministic"
    assert abs(gini1 - gini2) < 1e-10, "Gini not deterministic"
    print("Test 3 - Determinism: PASS")
    
    # Test 4: 분포 텔레메트리
    ranked_test = [(5.0, 0.0, "doc1", set()), (4.0, 0.0, "doc2", set()), (3.0, 0.0, "doc3", set())]
    telemetry = calculate_distribution_telemetry(ranked_test, 3)
    print(f"Test 4 - Telemetry: {json.dumps(telemetry, indent=2)}")
    
    sys.exit(0)

