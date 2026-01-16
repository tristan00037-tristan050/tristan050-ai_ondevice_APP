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
    
    # 숫자/문자열/불린/None만 허용 (원문/리스트 없음)
    allowed_types = (str, bool, int, float, type(None))
    for key, value in result.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
        # 문자열은 버킷 값 또는 reason_code만 허용
        if isinstance(value, str):
            valid_strings = ["HEALTHY", "COLLAPSED_UNIFORM", "COLLAPSED_DELTA", "UNKNOWN",
                            "VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH",
                            "LOW_INEQUALITY", "MEDIUM_INEQUALITY", "HIGH_INEQUALITY", "VERY_HIGH_INEQUALITY",
                            "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", "META_GUARD_SCHEMA_INVALID_FAILCLOSED",
                            "META_GUARD_COLLAPSED_UNIFORM", "META_GUARD_COLLAPSED_DELTA", "META_GUARD_UNKNOWN"]
            if key == "reason_code":
                # reason_code는 추가 reason_code 값도 허용
                assert value.startswith("META_GUARD_") or value in valid_strings, \
                    f"Invalid reason_code: {key}={value}"
            else:
                assert value in valid_strings, \
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


def test_enforce_missing_thresholds_file():
    """Enforce 모드: thresholds 파일 없음 => gate_allow=false (NO FAIL-OPEN)"""
    import tempfile
    import os
    from meta_guard import detect_distribution_collapse, THRESHOLDS_FILE
    
    # 임시로 thresholds 파일을 백업하고 제거
    original_path = THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Enforce 모드에서 thresholds 파일 없음 테스트
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        # Fail-Closed: gate_allow=false, reason_code 설정
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for missing thresholds, got {result['gate_allow']}"
        assert result["meta_guard_state"] == "UNKNOWN", \
            f"Expected UNKNOWN state, got {result['meta_guard_state']}"
        assert result["reason_code"] == "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", \
            f"Expected META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce missing thresholds file (fail-closed)")
    finally:
        # 복원
        if os.path.exists(backup_path):
            os.rename(backup_path, original_path)
        # 캐시 초기화
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_invalid_json():
    """Enforce 모드: invalid JSON => gate_allow=false (NO FAIL-OPEN)"""
    import tempfile
    import os
    from meta_guard import detect_distribution_collapse, THRESHOLDS_FILE, load_thresholds_with_validation
    
    # 임시로 invalid JSON 파일 생성
    original_path = THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Invalid JSON 파일 생성
        with open(original_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")
        
        # Enforce 모드에서 invalid JSON 테스트
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        # Fail-Closed: gate_allow=false
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for invalid JSON, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", \
            f"Expected META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce invalid JSON (fail-closed)")
    finally:
        # 복원
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        # 캐시 초기화
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_schema_invalid():
    """Enforce 모드: schema invalid (negative threshold) => gate_allow=false (NO FAIL-OPEN)"""
    import tempfile
    import json
    import os
    from meta_guard import detect_distribution_collapse, THRESHOLDS_FILE
    
    # 임시로 invalid schema 파일 생성
    original_path = THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Invalid schema (negative threshold) 파일 생성
        invalid_thresholds = {
            "collapse_detection": {
                "HEALTHY": {
                    "entropy_min": -0.1,  # 음수 (invalid)
                    "gini_max": 0.6,
                    "exclusive_gini_max": True
                },
                "COLLAPSED_UNIFORM": {
                    "entropy_max": 0.2,
                    "exclusive_entropy_max": True,
                    "gini_max": 0.4,
                    "exclusive_gini_max": True
                },
                "COLLAPSED_DELTA": {
                    "entropy_min": 0.8,
                    "gini_min": 0.8
                }
            }
        }
        with open(original_path, "w", encoding="utf-8") as f:
            json.dump(invalid_thresholds, f)
        
        # Enforce 모드에서 invalid schema 테스트
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        # Fail-Closed: gate_allow=false
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for invalid schema, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_SCHEMA_INVALID_FAILCLOSED", \
            f"Expected META_GUARD_SCHEMA_INVALID_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce schema invalid (fail-closed)")
    finally:
        # 복원
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        # 캐시 초기화
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_never_fail_open():
    """Enforce 모드: missing/invalid thresholds는 절대 gate_allow=true가 될 수 없음"""
    import tempfile
    import json
    import os
    from meta_guard import detect_distribution_collapse, THRESHOLDS_FILE
    
    original_path = THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    test_cases = [
        ("missing_file", None, None),
        ("invalid_json", "{ invalid }", None),
        ("missing_collapse_detection", {"version": "v1.0"}, None),
        ("negative_threshold", {
            "collapse_detection": {
                "HEALTHY": {"entropy_min": -0.1, "gini_max": 0.6},
                "COLLAPSED_UNIFORM": {"entropy_max": 0.2, "gini_max": 0.4},
                "COLLAPSED_DELTA": {"entropy_min": 0.8, "gini_min": 0.8}
            }
        }, None),
    ]
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        
        for case_name, file_content, _ in test_cases:
            # 파일 설정
            if case_name == "missing_file":
                if os.path.exists(original_path):
                    os.remove(original_path)
            else:
                with open(original_path, "w", encoding="utf-8") as f:
                    if isinstance(file_content, str):
                        f.write(file_content)
                    else:
                        json.dump(file_content, f)
            
            # Enforce 모드 테스트
            result = detect_distribution_collapse(scores, observe_only=False)
            
            # 절대 gate_allow=true가 될 수 없음
            assert result["gate_allow"] == False, \
                f"FAIL-OPEN detected in {case_name}: gate_allow={result['gate_allow']}"
            assert result["reason_code"] is not None, \
                f"Missing reason_code in {case_name}: {result}"
            
            # 캐시 초기화
            import meta_guard
            meta_guard._thresholds_cache = None
            meta_guard._thresholds_err_cache = None
        
        print("PASS: enforce never fail-open")
    finally:
        # 복원
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        # 캐시 초기화
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def main():
    """모든 테스트 실행"""
    tests = [
        test_meta_guard_deterministic,
        test_observe_only_behavior,
        test_meta_guard_meta_only,
        test_meta_guard_states,
        test_enforce_missing_thresholds_file,
        test_enforce_invalid_json,
        test_enforce_schema_invalid,
        test_enforce_never_fail_open,
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

