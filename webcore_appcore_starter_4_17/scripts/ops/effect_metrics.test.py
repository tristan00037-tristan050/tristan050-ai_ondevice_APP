#!/usr/bin/env python3
"""
Effect Metrics Unit Tests
"""

import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from effect_metrics import (
    calculate_ndcg,
    bucketize_ndcg,
    bucketize_ndcg_gain,
    calculate_ips_bucket,
    calculate_effect_metrics,
)


def test_ndcg_calculation():
    """NDCG 계산 검증"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    ndcg = calculate_ndcg(ranked, relevant_docs, 3)
    assert 0.0 <= ndcg <= 1.0, f"NDCG out of range: {ndcg}"
    
    # Ideal case: 모든 relevant가 상위에 위치
    ideal_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (2.0, 0.2, "doc3", set()),
    ]
    ideal_ndcg = calculate_ndcg(ideal_ranked, relevant_docs, 3)
    assert ideal_ndcg == 1.0, f"Ideal NDCG should be 1.0, got {ideal_ndcg}"
    
    print("PASS: NDCG calculation")


def test_bucketization_deterministic():
    """버킷화 결정론적 검증"""
    assert bucketize_ndcg(0.95) == "EXCELLENT"
    assert bucketize_ndcg(0.75) == "GOOD"
    assert bucketize_ndcg(0.55) == "FAIR"
    assert bucketize_ndcg(0.35) == "POOR"
    assert bucketize_ndcg(0.15) == "VERY_POOR"
    
    assert bucketize_ndcg_gain(0.15) == "LARGE_GAIN"
    assert bucketize_ndcg_gain(0.08) == "MEDIUM_GAIN"
    assert bucketize_ndcg_gain(0.03) == "SMALL_GAIN"
    assert bucketize_ndcg_gain(0.0) == "NEUTRAL"
    assert bucketize_ndcg_gain(-0.03) == "SMALL_LOSS"
    assert bucketize_ndcg_gain(-0.08) == "MEDIUM_LOSS"
    assert bucketize_ndcg_gain(-0.15) == "LARGE_LOSS"
    
    print("PASS: bucketization deterministic")


def test_effect_metrics_meta_only():
    """Effect metrics가 meta-only인지 검증"""
    baseline = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    variant = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    metrics = calculate_effect_metrics(baseline, variant, relevant_docs, 3)
    
    # 필수 키 확인
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
    assert "baseline_ranked" not in metrics
    assert "variant_ranked" not in metrics
    
    print("PASS: effect metrics meta-only")


def test_ndcg_gain_calculation():
    """NDCG gain 계산 검증"""
    # Baseline: doc1, doc2가 relevant
    baseline = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    # Variant: 동일 (gain = 0)
    variant_same = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    # Variant: 개선 (doc2가 위로)
    variant_improved = [
        (5.0, 0.5, "doc1", set()),
        (4.5, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    metrics_same = calculate_effect_metrics(baseline, variant_same, relevant_docs, 3)
    metrics_improved = calculate_effect_metrics(baseline, variant_improved, relevant_docs, 3)
    
    # 같은 랭킹이면 gain은 NEUTRAL 또는 작은 차이
    assert metrics_same["ndcg_at_k_gain_bucket"] in ["NEUTRAL", "SMALL_GAIN", "SMALL_LOSS"]
    
    print("PASS: NDCG gain calculation")


def main():
    """모든 테스트 실행"""
    tests = [
        test_ndcg_calculation,
        test_bucketization_deterministic,
        test_effect_metrics_meta_only,
        test_ndcg_gain_calculation,
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

