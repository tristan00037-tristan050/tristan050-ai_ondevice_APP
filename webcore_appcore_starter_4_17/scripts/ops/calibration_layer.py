#!/usr/bin/env python3
"""
Calibration Layer: 확률 공간으로의 매핑 (Shadow only, 행동 변경 없음)
현재는 identity mapping으로 고정하여 결과 동일 유지
"""

from typing import List, Tuple, Dict


def map_score_to_probability(primary: float, secondary: float, version: str = "v1.0-identity") -> float:
    """
    Score를 확률 공간으로 매핑 (현재는 identity mapping)
    
    Args:
        primary: Primary score
        secondary: Secondary score
        version: Calibration 버전 (현재는 identity만)
    
    Returns:
        확률 공간의 값 (현재는 primary 그대로 반환)
    """
    # 현재는 identity mapping (행동 변경 없음)
    if version == "v1.0-identity":
        return primary
    else:
        # 향후 다른 버전 추가 가능
        return primary


def calculate_calibration_curve_bucket(calibration_errors: List[float]) -> str:
    """
    Calibration curve bucket 계산 (meta-only)
    
    Args:
        calibration_errors: 각 쿼리별 calibration error 리스트
    
    Returns:
        버킷 문자열
    """
    if not calibration_errors:
        return "UNKNOWN"
    
    # 평균 calibration error 계산
    avg_error = sum(calibration_errors) / len(calibration_errors)
    
    # 버킷화
    if avg_error < 0.05:
        return "EXCELLENT"
    elif avg_error < 0.10:
        return "GOOD"
    elif avg_error < 0.20:
        return "FAIR"
    elif avg_error < 0.30:
        return "POOR"
    else:
        return "VERY_POOR"


def calculate_ece(expected_calibration_error: float) -> str:
    """
    Expected Calibration Error (ECE) bucket 계산 (meta-only)
    
    Args:
        expected_calibration_error: ECE 값 (0~1)
    
    Returns:
        버킷 문자열
    """
    if expected_calibration_error < 0.05:
        return "EXCELLENT"
    elif expected_calibration_error < 0.10:
        return "GOOD"
    elif expected_calibration_error < 0.20:
        return "FAIR"
    elif expected_calibration_error < 0.30:
        return "POOR"
    else:
        return "VERY_POOR"


def calculate_calibration_telemetry(
    ranked_before: List[Tuple[float, float, str, set]],
    ranked_after: List[Tuple[float, float, str, set]],
    relevant_docs: set,
    k: int
) -> Dict:
    """
    Calibration 진단 지표 계산 (meta-only, Shadow only)
    
    Args:
        ranked_before: Calibration 전 랭킹
        ranked_after: Calibration 후 랭킹 (현재는 동일)
        relevant_docs: Relevant document ID 집합
        k: topK 값
    
    Returns:
        meta-only calibration 지표 딕셔너리
    """
    # 현재는 identity mapping이므로 ranked_before와 ranked_after는 동일해야 함
    # 이는 Shadow only 검증용
    
    calibration_errors = []
    
    # 각 위치별 calibration error 계산 (간단한 휴리스틱)
    # 실제 calibration은 확률과 실제 relevance 간의 차이를 측정
    # Shadow only이므로 실제 relevance 정보가 없으면 0으로 가정
    for i, (primary, secondary, did, dt) in enumerate(ranked_before[:k], 1):
        # 확률 공간으로 매핑 (현재는 identity)
        prob = map_score_to_probability(primary, secondary, "v1.0-identity")
        
        # 실제 relevance (shadow only이므로 간단한 휴리스틱)
        # 실제로는 ground truth와 비교해야 하지만, shadow only이므로 0으로 가정
        actual_relevance = 1.0 if str(did) in relevant_docs else 0.0
        
        # Calibration error: |prob - actual_relevance|
        error = abs(prob - actual_relevance)
        calibration_errors.append(error)
    
    # ECE 계산 (간단한 평균)
    ece = sum(calibration_errors) / len(calibration_errors) if calibration_errors else 0.0
    
    return {
        "calibration_curve_bucket": calculate_calibration_curve_bucket(calibration_errors),
        "ece_bucket": calculate_ece(ece),
        "score_to_prob_version": "v1.0-identity",
    }


if __name__ == "__main__":
    # Unit test용
    # Test 1: Identity mapping 검증
    primary_test = 5.0
    secondary_test = 0.5
    prob = map_score_to_probability(primary_test, secondary_test, "v1.0-identity")
    assert prob == primary_test, f"Identity mapping failed: {prob} != {primary_test}"
    print("PASS: identity mapping")
    
    # Test 2: Calibration telemetry meta-only 검증
    ranked_test = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs_test = {"doc1", "doc2"}
    telemetry = calculate_calibration_telemetry(ranked_test, ranked_test, relevant_docs_test, 3)
    
    assert "calibration_curve_bucket" in telemetry
    assert "ece_bucket" in telemetry
    assert "score_to_prob_version" in telemetry
    assert telemetry["score_to_prob_version"] == "v1.0-identity"
    
    # Meta-only 검증 (문자열만)
    allowed_types = (str,)
    for key, value in telemetry.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
    
    print("PASS: calibration telemetry meta-only")
    print("OK: Calibration layer tests passed")

