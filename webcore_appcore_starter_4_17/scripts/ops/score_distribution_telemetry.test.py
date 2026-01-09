#!/usr/bin/env python3
"""
Score Distribution Telemetry Unit Tests
결정론적 검증 (D0): 동일 입력에 대해 항상 동일한 결과
"""

import json
import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_distribution_telemetry import (
    percentile,
    calculate_gaps,
    calculate_entropy,
    calculate_gini,
    bucketize_entropy,
    bucketize_gini,
    bucketize_unique_count,
    calculate_distribution_telemetry,
)


def test_percentile_deterministic():
    """Percentile 계산이 결정론적인지 검증"""
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    p25_1 = percentile(data, 0.25)
    p25_2 = percentile(data, 0.25)
    assert abs(p25_1 - p25_2) < 1e-10, f"Percentile not deterministic: {p25_1} != {p25_2}"
    print("PASS: percentile deterministic")


def test_entropy_deterministic():
    """엔트로피 계산이 결정론적인지 검증"""
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    entropy1 = calculate_entropy(scores)
    entropy2 = calculate_entropy(scores)
    assert abs(entropy1 - entropy2) < 1e-10, f"Entropy not deterministic: {entropy1} != {entropy2}"
    print("PASS: entropy deterministic")


def test_gini_deterministic():
    """지니 계수 계산이 결정론적인지 검증"""
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    gini1 = calculate_gini(scores)
    gini2 = calculate_gini(scores)
    assert abs(gini1 - gini2) < 1e-10, f"Gini not deterministic: {gini1} != {gini2}"
    print("PASS: gini deterministic")


def test_bucketize_deterministic():
    """버킷화가 결정론적인지 검증"""
    entropy = 0.5
    bucket1 = bucketize_entropy(entropy)
    bucket2 = bucketize_entropy(entropy)
    assert bucket1 == bucket2, f"Entropy bucket not deterministic: {bucket1} != {bucket2}"
    
    gini = 0.5
    gini_bucket1 = bucketize_gini(gini)
    gini_bucket2 = bucketize_gini(gini)
    assert gini_bucket1 == gini_bucket2, f"Gini bucket not deterministic: {gini_bucket1} != {gini_bucket2}"
    
    unique_bucket1 = bucketize_unique_count(3, 5)
    unique_bucket2 = bucketize_unique_count(3, 5)
    assert unique_bucket1 == unique_bucket2, f"Unique count bucket not deterministic: {unique_bucket1} != {unique_bucket2}"
    
    print("PASS: bucketize deterministic")


def test_telemetry_deterministic():
    """전체 텔레메트리 계산이 결정론적인지 검증"""
    ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
        (2.0, 0.0, "doc4", set()),
        (1.0, 0.0, "doc5", set()),
    ]
    
    telemetry1 = calculate_distribution_telemetry(ranked, 5)
    telemetry2 = calculate_distribution_telemetry(ranked, 5)
    
    assert telemetry1 == telemetry2, f"Telemetry not deterministic: {telemetry1} != {telemetry2}"
    print("PASS: telemetry deterministic")


def test_telemetry_meta_only():
    """텔레메트리 출력이 meta-only인지 검증 (원문/문장/리스트 없음)"""
    ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    
    telemetry = calculate_distribution_telemetry(ranked, 2)
    
    # 숫자/버킷만 허용
    allowed_types = (int, float, str)
    for key, value in telemetry.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
        # 문자열은 버킷 값만 허용
        if isinstance(value, str):
            assert value in ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH", 
                            "LOW_INEQUALITY", "MEDIUM_INEQUALITY", "HIGH_INEQUALITY", "VERY_HIGH_INEQUALITY",
                            "LOW_DIVERSITY", "MEDIUM_DIVERSITY", "HIGH_DIVERSITY"], \
                f"Invalid bucket value: {key}={value}"
    
    print("PASS: telemetry meta-only")


def main():
    """모든 테스트 실행"""
    tests = [
        test_percentile_deterministic,
        test_entropy_deterministic,
        test_gini_deterministic,
        test_bucketize_deterministic,
        test_telemetry_deterministic,
        test_telemetry_meta_only,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {e}")
            failed += 1
    
    print(f"\n결과: {passed} PASS, {failed} FAIL")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

