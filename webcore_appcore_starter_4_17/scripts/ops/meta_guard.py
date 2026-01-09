#!/usr/bin/env python3
"""
Meta-Guard: 분포 붕괴 감지 및 GTB 개입 Fail-Closed 비활성화
기본 원칙: 분포가 붕괴로 판단되면 GTB 개입을 Fail-Closed로 비활성화 (=개입하지 않음)
"""

import math
from typing import List, Tuple, Dict


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


def detect_distribution_collapse(
    scores: List[float],
    observe_only: bool = True
) -> Dict:
    """
    분포 붕괴 감지 (Meta-Guard)
    
    Args:
        scores: Primary score 리스트
        observe_only: True면 행동 변경 없이 관찰만 (이번 PR은 True 고정)
    
    Returns:
        meta-only 딕셔너리:
        - meta_guard_state: HEALTHY / COLLAPSED_UNIFORM / COLLAPSED_DELTA / UNKNOWN
        - gate_allow: bool (observe_only=True면 항상 True, 실제 차단은 다음 PR)
        - entropy_bucket: str
        - gini_bucket: str
    """
    if not scores or len(scores) == 0:
        return {
            "meta_guard_state": "UNKNOWN",
            "gate_allow": True,  # observe_only=True면 항상 True
            "entropy_bucket": "VERY_LOW",
            "gini_bucket": "LOW_INEQUALITY",
        }
    
    # 엔트로피 및 지니 계산
    entropy = calculate_entropy(scores)
    gini = calculate_gini(scores)
    
    entropy_bucket = bucketize_entropy(entropy)
    gini_bucket = bucketize_gini(gini)
    
    # 분포 붕괴 판정 (observe_only=True면 임계치 확정 전이므로 관찰만)
    # 초기 버전: 임계치는 Evidence Owner가 확정 후 다음 PR에서 enforce
    # 이번 PR은 observe_only=True로 고정하여 행동 변경 없음
    
    # 임시 판정 로직 (관찰용, 실제 차단은 다음 PR)
    # COLLAPSED_UNIFORM: 엔트로피가 매우 낮음 (모든 점수가 거의 동일)
    # COLLAPSED_DELTA: 지니 계수가 매우 낮음 (분포가 균등)
    # HEALTHY: 정상 분포
    
    state = "UNKNOWN"
    
    # 임시 임계치 (관찰용, Evidence Owner가 확정 후 다음 PR에서 enforce)
    # 이번 PR은 observe_only=True이므로 실제 차단 없음
    if entropy < 0.1:  # 임시 임계치 (관찰용)
        state = "COLLAPSED_UNIFORM"
    elif gini < 0.1:  # 임시 임계치 (관찰용)
        state = "COLLAPSED_DELTA"
    elif entropy >= 0.2 and gini >= 0.2:  # 임시 임계치 (관찰용)
        state = "HEALTHY"
    else:
        state = "UNKNOWN"
    
    # gate_allow: observe_only=True면 항상 True (행동 변경 없음)
    # 실제 차단은 Evidence Owner가 임계치 확정 후 다음 PR에서 enforce
    gate_allow = True if observe_only else (state == "HEALTHY")
    
    return {
        "meta_guard_state": state,
        "gate_allow": gate_allow,
        "entropy_bucket": entropy_bucket,
        "gini_bucket": gini_bucket,
    }


def calculate_meta_guard_for_query(
    ranked: List[Tuple[float, float, str, set]],
    k: int,
    observe_only: bool = True
) -> Dict:
    """
    쿼리별 Meta-Guard 계산
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (이미 정렬됨)
        k: topK 값
        observe_only: True면 행동 변경 없이 관찰만 (이번 PR은 True 고정)
    
    Returns:
        meta-only 딕셔너리
    """
    if not ranked or len(ranked) == 0:
        return {
            "meta_guard_state": "UNKNOWN",
            "gate_allow": True,
            "entropy_bucket": "VERY_LOW",
            "gini_bucket": "LOW_INEQUALITY",
        }
    
    topk_ranked = ranked[:k]
    primary_scores = [p for p, _, _, _ in topk_ranked]
    
    return detect_distribution_collapse(primary_scores, observe_only=observe_only)


if __name__ == "__main__":
    # Unit test용
    # Test 1: 결정론적 검증
    scores_test = [5.0, 4.0, 3.0, 2.0, 1.0]
    result1 = detect_distribution_collapse(scores_test, observe_only=True)
    result2 = detect_distribution_collapse(scores_test, observe_only=True)
    
    assert result1 == result2, f"Not deterministic: {result1} != {result2}"
    print("PASS: Meta-Guard deterministic")
    
    # Test 2: observe_only=True면 gate_allow는 항상 True
    assert result1["gate_allow"] == True, f"gate_allow should be True when observe_only=True: {result1}"
    print("PASS: gate_allow=True when observe_only=True")
    
    # Test 3: meta-only 검증
    allowed_types = (str, bool)
    for key, value in result1.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
    print("PASS: Meta-Guard meta-only")
    
    print("OK: Meta-Guard tests passed")

