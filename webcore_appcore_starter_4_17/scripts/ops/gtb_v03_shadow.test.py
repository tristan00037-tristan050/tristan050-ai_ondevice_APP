#!/usr/bin/env python3
"""
GTB v0.3 Shadow Mode Unit Tests
D0 결정론 검증: 동일 입력에 대해 항상 동일한 결과
"""

import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gtb_v03_shadow import (
    calculate_swap_budget,
    calculate_gap_p25_for_query,
    is_near_tie,
    simulate_gtb_v03_shadow,
)


def test_swap_budget_deterministic():
    """Swap budget 계산이 결정론적인지 검증"""
    k = 20
    budget1 = calculate_swap_budget(k)
    budget2 = calculate_swap_budget(k)
    assert budget1 == budget2, f"Swap budget not deterministic: {budget1} != {budget2}"
    assert budget1 == min(3, int(20 * 0.1)) == 2, f"Swap budget incorrect: {budget1}"
    print("PASS: swap budget deterministic")


def test_gap_p25_deterministic():
    """Gap_p25 계산이 결정론적인지 검증"""
    ranked = [
        (5.0, 0.0, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    gap_p25_1 = calculate_gap_p25_for_query(ranked, 3)
    gap_p25_2 = calculate_gap_p25_for_query(ranked, 3)
    assert abs(gap_p25_1 - gap_p25_2) < 1e-10, f"Gap_p25 not deterministic: {gap_p25_1} != {gap_p25_2}"
    print("PASS: gap_p25 deterministic")


def test_gtb_shadow_deterministic():
    """GTB v0.3 Shadow Mode 시뮬레이션이 결정론적인지 검증"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (5.0, 0.3, "doc2", set()),  # near-tie (gap=0)
        (4.0, 0.0, "doc3", set()),
    ]
    gap_p25 = 0.0
    relevant_docs = {"doc1", "doc2"}
    baseline_ranked = ["doc1", "doc2", "doc3"]
    
    result1 = simulate_gtb_v03_shadow(ranked, 3, gap_p25, relevant_docs, baseline_ranked)
    result2 = simulate_gtb_v03_shadow(ranked, 3, gap_p25, relevant_docs, baseline_ranked)
    
    assert result1 == result2, f"GTB shadow not deterministic: {result1} != {result2}"
    print("PASS: GTB shadow deterministic")


def test_gtb_shadow_meta_only():
    """GTB v0.3 Shadow Mode 출력이 meta-only인지 검증 (카운트만)"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (5.0, 0.3, "doc2", set()),
        (4.0, 0.0, "doc3", set()),
    ]
    gap_p25 = 0.0
    relevant_docs = {"doc1", "doc2"}
    baseline_ranked = ["doc1", "doc2", "doc3"]
    
    result = simulate_gtb_v03_shadow(ranked, 3, gap_p25, relevant_docs, baseline_ranked)
    
    # 숫자/불린/문자열(빈 문자열 또는 reason_code)만 허용 (원문/리스트 없음)
    allowed_types = (int, bool, str)
    for key, value in result.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
        if isinstance(value, str):
            assert key == "shadow_reason_code", f"Unexpected string key: {key}"
    
    # 필수 키 확인
    required_keys = ["would_move_up_count", "would_move_down_count", "proposed_swap_count", "budget_hit_count", "shadow_reason_code"]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"
    
    print("PASS: GTB shadow meta-only")


def test_budget_hit():
    """Budget hit 검증"""
    # K=5일 때 max_swaps = min(3, floor(5*0.1)) = 0
    budget = calculate_swap_budget(5)
    assert budget == 0, f"Budget for K=5 should be 0, got {budget}"
    
    # K=20일 때 max_swaps = min(3, floor(20*0.1)) = 2
    budget = calculate_swap_budget(20)
    assert budget == 2, f"Budget for K=20 should be 2, got {budget}"
    
    # K=50일 때 max_swaps = min(3, floor(50*0.1)) = 3
    budget = calculate_swap_budget(50)
    assert budget == 3, f"Budget for K=50 should be 3, got {budget}"
    
    print("PASS: budget hit calculation")


def test_primary_sorted_invariance():
    """Primary-sorted invariance 검증: 입력 순서와 무관하게 동일한 카운터"""
    # 의도적으로 primary-monotonic이 아닌 입력 생성
    ranked_inverted = [
        (3.0, 0.0, "doc3", set()),  # 낮은 primary
        (5.0, 0.5, "doc1", set()),  # 높은 primary
        (4.0, 0.0, "doc2", set()),  # 중간 primary
    ]
    
    # 명시적으로 primary-sorted된 버전
    ranked_sorted = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
        (3.0, 0.0, "doc3", set()),
    ]
    
    gap_p25 = 0.0  # 모든 gap이 near-tie
    relevant_docs = {"doc1", "doc2", "doc3"}
    baseline_ranked = ["doc1", "doc2", "doc3"]
    
    result_inverted = simulate_gtb_v03_shadow(ranked_inverted, 3, gap_p25, relevant_docs, baseline_ranked)
    result_sorted = simulate_gtb_v03_shadow(ranked_sorted, 3, gap_p25, relevant_docs, baseline_ranked)
    
    # 카운터가 동일해야 함
    assert result_inverted["would_move_up_count"] == result_sorted["would_move_up_count"], \
        f"would_move_up_count mismatch: {result_inverted['would_move_up_count']} != {result_sorted['would_move_up_count']}"
    assert result_inverted["would_move_down_count"] == result_sorted["would_move_down_count"], \
        f"would_move_down_count mismatch: {result_inverted['would_move_down_count']} != {result_sorted['would_move_down_count']}"
    assert result_inverted["proposed_swap_count"] == result_sorted["proposed_swap_count"], \
        f"proposed_swap_count mismatch: {result_inverted['proposed_swap_count']} != {result_sorted['proposed_swap_count']}"
    assert result_inverted["budget_hit_count"] == result_sorted["budget_hit_count"], \
        f"budget_hit_count mismatch: {result_inverted['budget_hit_count']} != {result_sorted['budget_hit_count']}"
    
    print("PASS: primary-sorted invariance")


def test_fail_closed_primary_missing():
    """Fail-Closed: primary_score missing/non-finite 처리"""
    # NaN 테스트
    ranked_nan = [
        (float('nan'), 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    
    result = simulate_gtb_v03_shadow(ranked_nan, 2, 0.0, set(), [])
    assert result["shadow_reason_code"] == "GTB_SHADOW_PRIMARY_MISSING", \
        f"Expected GTB_SHADOW_PRIMARY_MISSING, got {result['shadow_reason_code']}"
    assert result["would_move_up_count"] == 0
    assert result["proposed_swap_count"] == 0
    
    # Inf 테스트
    ranked_inf = [
        (float('inf'), 0.5, "doc1", set()),
        (4.0, 0.0, "doc2", set()),
    ]
    
    result = simulate_gtb_v03_shadow(ranked_inf, 2, 0.0, set(), [])
    assert result["shadow_reason_code"] == "GTB_SHADOW_PRIMARY_MISSING", \
        f"Expected GTB_SHADOW_PRIMARY_MISSING, got {result['shadow_reason_code']}"
    
    print("PASS: fail-closed primary missing")


def main():
    """모든 테스트 실행"""
    tests = [
        test_swap_budget_deterministic,
        test_gap_p25_deterministic,
        test_gtb_shadow_deterministic,
        test_gtb_shadow_meta_only,
        test_budget_hit,
        test_primary_sorted_invariance,
        test_fail_closed_primary_missing,
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

