#!/usr/bin/env python3
"""
Meta-Guard Unit Tests
D0 결정론 검증: 동일 입력에 대해 항상 동일한 결과
observe_only=True 검증: 행동 변경 없음
"""

import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meta_guard import (
    calculate_entropy,
    calculate_gini,
    bucketize_entropy,
    bucketize_gini,
    detect_distribution_collapse,
    calculate_meta_guard_for_query,
)


def test_meta_guard_deterministic():
    """Meta-Guard 계산이 결정론적인지 검증"""
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    result1 = detect_distribution_collapse(scores, observe_only=True)
    result2 = detect_distribution_collapse(scores, observe_only=True)
    
    assert result1 == result2, f"Meta-Guard not deterministic: {result1} != {result2}"
    print("PASS: meta-guard deterministic")


def test_observe_only_behavior():
    """observe_only=True면 gate_allow는 항상 True인지 검증"""
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    result = detect_distribution_collapse(scores, observe_only=True)
    
    assert result["gate_allow"] == True, f"gate_allow should be True when observe_only=True: {result}"
    print("PASS: observe_only=True behavior")


def test_meta_guard_meta_only():
    """Meta-Guard 출력이 meta-only인지 검증 (원문 출력 없음)"""
    scores = [5.0, 4.0, 3.0]
    result = detect_distribution_collapse(scores, observe_only=True)
    
    # 숫자/문자열/불린만 허용 (원문/리스트 없음)
    allowed_types = (str, bool, int, float)
    for key, value in result.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
        # 문자열은 버킷 값만 허용
        if isinstance(value, str):
            assert value in ["HEALTHY", "COLLAPSED_UNIFORM", "COLLAPSED_DELTA", "UNKNOWN",
                            "VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH",
                            "LOW_INEQUALITY", "MEDIUM_INEQUALITY", "HIGH_INEQUALITY", "VERY_HIGH_INEQUALITY"], \
                f"Invalid value: {key}={value}"
    
    print("PASS: meta-guard meta-only")


def test_meta_guard_states():
    """Meta-Guard 상태가 올바른지 검증"""
    # 유효한 상태 값 확인
    valid_states = ["HEALTHY", "COLLAPSED_UNIFORM", "COLLAPSED_DELTA", "UNKNOWN"]
    
    # HEALTHY 케이스
    scores_healthy = [5.0, 4.0, 3.0, 2.0, 1.0]
    result_healthy = detect_distribution_collapse(scores_healthy, observe_only=True)
    assert result_healthy["meta_guard_state"] in valid_states, \
        f"Expected valid state, got {result_healthy['meta_guard_state']}"
    
    # COLLAPSED_UNIFORM 케이스 (엔트로피 매우 낮음)
    scores_uniform = [1.0, 1.0, 1.0, 1.0, 1.0]
    result_uniform = detect_distribution_collapse(scores_uniform, observe_only=True)
    assert result_uniform["meta_guard_state"] in valid_states, \
        f"Expected valid state, got {result_uniform['meta_guard_state']}"
    
    print("PASS: meta-guard states")


def main():
    """모든 테스트 실행"""
    tests = [
        test_meta_guard_deterministic,
        test_observe_only_behavior,
        test_meta_guard_meta_only,
        test_meta_guard_states,
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

