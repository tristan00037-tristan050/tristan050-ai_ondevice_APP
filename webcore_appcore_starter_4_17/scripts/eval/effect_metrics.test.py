#!/usr/bin/env python3
"""
Effect Metrics Unit Tests
- Deterministic calculation
- Fail-Closed behavior
- Meta-only output
"""

import sys
import os
import math

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from effect_metrics import (
    calculate_ndcg_at_k,
    calculate_ips,
    calculate_snips,
    calculate_effect_metrics,
)


def test_ndcg_gain_positive():
    """Toy ranking where treatment improves top relevance -> ndcg_gain positive and exact numeric check"""
    # Baseline: doc1 (relevant) at position 2, doc2 (not relevant) at position 1
    baseline_ranked = [
        (5.0, 0.0, "doc2", set()),
        (4.0, 0.0, "doc1", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    
    # Treatment: doc1 (relevant) at position 1, doc2 (not relevant) at position 2
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    
    # Graded relevance labels
    relevance_labels = {
        "doc1": 1.0,  # relevant
        "doc2": 0.0,  # not relevant
        "doc3": 0.0,  # not relevant
    }
    
    k = 3
    
    # Baseline NDCG
    ndcg_baseline = calculate_ndcg_at_k(baseline_ranked, relevance_labels, k)
    assert ndcg_baseline is not None, "Baseline NDCG should not be None"
    assert 0.0 <= ndcg_baseline <= 1.0, f"Baseline NDCG out of range: {ndcg_baseline}"
    
    # Treatment NDCG
    ndcg_treatment = calculate_ndcg_at_k(treatment_ranked, relevance_labels, k)
    assert ndcg_treatment is not None, "Treatment NDCG should not be None"
    assert 0.0 <= ndcg_treatment <= 1.0, f"Treatment NDCG out of range: {ndcg_treatment}"
    
    # Treatment should have higher NDCG (relevant doc at position 1)
    assert ndcg_treatment > ndcg_baseline, \
        f"Treatment NDCG should be higher than baseline: {ndcg_treatment} <= {ndcg_baseline}"
    
    # Exact numeric check
    # Baseline: doc1 at position 2 -> DCG = 1.0 / log2(3) = 1.0 / 1.585 = 0.631
    # IDCG: doc1 at position 1 -> IDCG = 1.0 / log2(2) = 1.0 / 1.0 = 1.0
    # Baseline NDCG = 0.631 / 1.0 = 0.631
    
    # Treatment: doc1 at position 1 -> DCG = 1.0 / log2(2) = 1.0 / 1.0 = 1.0
    # IDCG = 1.0
    # Treatment NDCG = 1.0 / 1.0 = 1.0
    
    # Gain = 1.0 - 0.631 = 0.369
    expected_gain = 1.0 - (1.0 / math.log2(3))
    actual_gain = ndcg_treatment - ndcg_baseline
    
    assert abs(actual_gain - expected_gain) < 1e-6, \
        f"NDCG gain mismatch: expected {expected_gain}, got {actual_gain}"
    
    print("PASS: NDCG gain positive and exact numeric check")


def test_missing_labels_fail_closed():
    """Missing labels -> ndcg outputs null, reason_code EFFECT_LABELS_MISSING"""
    baseline_ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    
    # Missing relevance_labels
    result = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, None, k=10
    )
    
    assert result["effect_ndcg_at_10_baseline"] is None, \
        "NDCG baseline should be None when labels missing"
    assert result["effect_ndcg_at_10_treatment"] is None, \
        "NDCG treatment should be None when labels missing"
    assert result["effect_ndcg_gain_at_10"] is None, \
        "NDCG gain should be None when labels missing"
    assert result["effect_reason_code"] == "EFFECT_LABELS_MISSING", \
        f"Expected EFFECT_LABELS_MISSING, got {result['effect_reason_code']}"
    
    print("PASS: missing labels fail-closed")


def test_propensity_missing_fail_closed():
    """Propensity missing or denom=0 -> ips/snips null, reason_code EFFECT_PROPENSITY_MISSING"""
    baseline_ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    relevance_labels = {"doc1": 1.0, "doc2": 0.0}
    
    # Missing propensities
    result = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels, k=10,
        logged_propensities=None, observed_rewards=None
    )
    
    assert result["effect_ips"] is None, \
        "IPS should be None when propensities missing"
    assert result["effect_snips"] is None, \
        "SNIPS should be None when propensities missing"
    assert result["effect_reason_code"] == "EFFECT_PROPENSITY_MISSING", \
        f"Expected EFFECT_PROPENSITY_MISSING, got {result['effect_reason_code']}"
    
    # denom=0 (propensity=0)
    logged_propensities = {"doc1": 0.0, "doc2": 0.0}  # All zero
    observed_rewards = {"doc1": 1.0, "doc2": 0.0}
    
    result2 = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels, k=10,
        logged_propensities=logged_propensities, observed_rewards=observed_rewards
    )
    
    assert result2["effect_ips"] is None, \
        "IPS should be None when propensity=0 (denom=0)"
    assert result2["effect_snips"] is None, \
        "SNIPS should be None when propensity=0 (denom=0)"
    assert result2["effect_reason_code"] == "EFFECT_PROPENSITY_MISSING", \
        f"Expected EFFECT_PROPENSITY_MISSING for denom=0, got {result2['effect_reason_code']}"
    
    print("PASS: propensity missing/denom=0 fail-closed")


def test_nan_inf_fail_closed():
    """NaN/inf anywhere -> fail-closed with EFFECT_NUMERIC_INVALID"""
    baseline_ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    
    # NaN in relevance labels
    relevance_labels_nan = {"doc1": float('nan'), "doc2": 0.0}
    result = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels_nan, k=10
    )
    assert result["effect_ndcg_at_10_baseline"] is None, \
        "NDCG should be None when relevance is NaN"
    assert result["effect_reason_code"] == "EFFECT_NUMERIC_INVALID", \
        f"Expected EFFECT_NUMERIC_INVALID for NaN, got {result['effect_reason_code']}"
    
    # Inf in relevance labels
    relevance_labels_inf = {"doc1": float('inf'), "doc2": 0.0}
    result2 = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels_inf, k=10
    )
    assert result2["effect_ndcg_at_10_baseline"] is None, \
        "NDCG should be None when relevance is Inf"
    assert result2["effect_reason_code"] == "EFFECT_NUMERIC_INVALID", \
        f"Expected EFFECT_NUMERIC_INVALID for Inf, got {result2['effect_reason_code']}"
    
    # NaN in propensities
    relevance_labels_ok = {"doc1": 1.0, "doc2": 0.0}
    logged_propensities_nan = {"doc1": float('nan'), "doc2": 0.5}
    observed_rewards_ok = {"doc1": 1.0, "doc2": 0.0}
    
    result3 = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels_ok, k=10,
        logged_propensities=logged_propensities_nan, observed_rewards=observed_rewards_ok
    )
    assert result3["effect_ips"] is None, \
        "IPS should be None when propensity is NaN"
    assert result3["effect_reason_code"] == "EFFECT_PROPENSITY_MISSING", \
        f"Expected EFFECT_PROPENSITY_MISSING for NaN propensity, got {result3['effect_reason_code']}"
    
    print("PASS: NaN/inf fail-closed")


def test_meta_only_output():
    """Output should be meta-only (numbers/null/reason_code only, no raw content)"""
    baseline_ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    relevance_labels = {"doc1": 1.0, "doc2": 0.0}
    
    result = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels, k=10
    )
    
    # Allowed types: numbers (int/float), None, strings (reason_code only)
    allowed_types = (int, float, type(None), str)
    for key, value in result.items():
        assert isinstance(value, allowed_types), \
            f"Non-meta-only value: {key}={value} (type: {type(value)})"
        if isinstance(value, str):
            assert key == "effect_reason_code", \
                f"Unexpected string key: {key}={value}"
    
    # No raw content
    assert "ranked" not in result
    assert "docs" not in result
    assert "query" not in result
    assert "labels" not in result
    
    print("PASS: meta-only output")


def test_deterministic():
    """Deterministic: same input -> same output"""
    baseline_ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    treatment_ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    relevance_labels = {"doc1": 1.0, "doc2": 0.0}
    
    result1 = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels, k=10
    )
    result2 = calculate_effect_metrics(
        baseline_ranked, treatment_ranked, relevance_labels, k=10
    )
    
    assert result1 == result2, \
        f"Results not deterministic: {result1} != {result2}"
    
    print("PASS: deterministic")


def main():
    """모든 테스트 실행"""
    tests = [
        test_ndcg_gain_positive,
        test_missing_labels_fail_closed,
        test_propensity_missing_fail_closed,
        test_nan_inf_fail_closed,
        test_meta_only_output,
        test_deterministic,
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

