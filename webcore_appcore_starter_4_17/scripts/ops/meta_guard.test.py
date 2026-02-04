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


def test_enforce_missing_frozen_thresholds_file():
    """Enforce 모드: frozen thresholds 파일 없음 => gate_allow=false (NO FAIL-OPEN)"""
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    # 임시로 frozen thresholds 파일을 백업하고 제거
    original_path = FROZEN_THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Enforce 모드에서 frozen thresholds 파일 없음 테스트
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        # Fail-Closed: gate_allow=false, reason_code 설정
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for missing frozen thresholds, got {result['gate_allow']}"
        assert result["meta_guard_state"] == "UNKNOWN", \
            f"Expected UNKNOWN state, got {result['meta_guard_state']}"
        assert result["reason_code"] == "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", \
            f"Expected META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce missing frozen thresholds file (fail-closed)")
    finally:
        # 복원
        if os.path.exists(backup_path):
            os.rename(backup_path, original_path)
        # 캐시 초기화
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_frozen_field_missing():
    """Enforce 모드: frozen 필드 없음 => gate_allow=false, reason_code=...NOT_FROZEN_FAILCLOSED"""
    import json
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    original_path = FROZEN_THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # frozen 필드 없는 파일 생성
        data_no_frozen = {
            "schema_version": "v1",
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {
                "collapse_detection": {
                    "HEALTHY": {"entropy_min": 0.4, "gini_max": 0.6, "exclusive_gini_max": True},
                    "COLLAPSED_UNIFORM": {"entropy_max": 0.2, "exclusive_entropy_max": True, "gini_max": 0.4, "exclusive_gini_max": True},
                    "COLLAPSED_DELTA": {"entropy_min": 0.8, "gini_min": 0.8}
                }
            }
        }
        with open(original_path, "w", encoding="utf-8") as f:
            json.dump(data_no_frozen, f)
        
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for missing frozen field, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_THRESHOLDS_NOT_FROZEN_FAILCLOSED", \
            f"Expected META_GUARD_THRESHOLDS_NOT_FROZEN_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce frozen field missing (fail-closed)")
    finally:
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_frozen_false():
    """Enforce 모드: frozen=false => gate_allow=false"""
    import json
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    original_path = FROZEN_THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # frozen=false 파일 생성
        data_frozen_false = {
            "schema_version": "v1",
            "frozen": False,
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {
                "collapse_detection": {
                    "HEALTHY": {"entropy_min": 0.4, "gini_max": 0.6, "exclusive_gini_max": True},
                    "COLLAPSED_UNIFORM": {"entropy_max": 0.2, "exclusive_entropy_max": True, "gini_max": 0.4, "exclusive_gini_max": True},
                    "COLLAPSED_DELTA": {"entropy_min": 0.8, "gini_min": 0.8}
                }
            }
        }
        with open(original_path, "w", encoding="utf-8") as f:
            json.dump(data_frozen_false, f)
        
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for frozen=false, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_THRESHOLDS_NOT_FROZEN_FAILCLOSED", \
            f"Expected META_GUARD_THRESHOLDS_NOT_FROZEN_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce frozen=false (fail-closed)")
    finally:
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_valid_frozen_file():
    """Enforce 모드: valid frozen file => gate_allow depends on metrics (normal path)"""
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    # Valid frozen file이 이미 존재해야 함
    if not os.path.exists(FROZEN_THRESHOLDS_FILE):
        print("SKIP: frozen thresholds file not found")
        return
    
    # HEALTHY 케이스
    scores_healthy = [5.0, 4.0, 3.0, 2.0, 1.0]
    result = detect_distribution_collapse(scores_healthy, observe_only=False)
    
    # Valid frozen file이면 정상 평가
    assert "thresholds_schema_version" in result, "Missing thresholds_schema_version"
    assert "thresholds_fingerprint" in result, "Missing thresholds_fingerprint"
    assert result["thresholds_schema_version"] == "v1", \
        f"Expected schema_version=v1, got {result['thresholds_schema_version']}"
    assert result["thresholds_fingerprint"] is not None, \
        f"Expected fingerprint, got {result['thresholds_fingerprint']}"
    
    # HEALTHY면 gate_allow=True
    if result["meta_guard_state"] == "HEALTHY":
        assert result["gate_allow"] == True, \
            f"Expected gate_allow=True for HEALTHY, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_OK", \
            f"Expected reason_code=META_GUARD_OK, got {result['reason_code']}"
    
    print("PASS: enforce valid frozen file (normal path)")


def test_fingerprint_stable():
    """Fingerprint가 동일한 파일에 대해 안정적인지 검증"""
    import json
    import os
    from meta_guard import calculate_thresholds_fingerprint, FROZEN_THRESHOLDS_FILE
    
    if not os.path.exists(FROZEN_THRESHOLDS_FILE):
        print("SKIP: frozen thresholds file not found")
        return
    
    with open(FROZEN_THRESHOLDS_FILE, "r", encoding="utf-8") as f:
        data1 = json.load(f)
    
    # 동일한 파일을 다시 로드
    with open(FROZEN_THRESHOLDS_FILE, "r", encoding="utf-8") as f:
        data2 = json.load(f)
    
    fp1 = calculate_thresholds_fingerprint(data1)
    fp2 = calculate_thresholds_fingerprint(data2)
    
    assert fp1 == fp2, f"Fingerprint not stable: {fp1} != {fp2}"
    
    print("PASS: fingerprint stable")


def test_enforce_frozen_schema_invalid():
    """Enforce 모드: frozen schema invalid (negative threshold) => gate_allow=false (NO FAIL-OPEN)"""
    import json
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    original_path = FROZEN_THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Invalid schema (negative threshold) frozen 파일 생성
        invalid_frozen = {
            "schema_version": "v1",
            "frozen": True,
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {
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
        }
        with open(original_path, "w", encoding="utf-8") as f:
            json.dump(invalid_frozen, f)
        
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = detect_distribution_collapse(scores, observe_only=False)
        
        assert result["gate_allow"] == False, \
            f"Expected gate_allow=False for invalid frozen schema, got {result['gate_allow']}"
        assert result["reason_code"] == "META_GUARD_SCHEMA_INVALID_FAILCLOSED", \
            f"Expected META_GUARD_SCHEMA_INVALID_FAILCLOSED, got {result['reason_code']}"
        
        print("PASS: enforce frozen schema invalid (fail-closed)")
    finally:
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        import meta_guard
        meta_guard._thresholds_cache = None
        meta_guard._thresholds_err_cache = None


def test_enforce_never_fail_open_frozen():
    """Enforce 모드: missing/invalid frozen thresholds는 절대 gate_allow=true가 될 수 없음"""
    import json
    import os
    from meta_guard import detect_distribution_collapse, FROZEN_THRESHOLDS_FILE
    
    original_path = FROZEN_THRESHOLDS_FILE
    backup_path = original_path + ".backup"
    
    test_cases = [
        ("missing_file", None),
        ("invalid_json", "{ invalid }"),
        ("missing_frozen", {
            "schema_version": "v1",
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {"collapse_detection": {"HEALTHY": {}, "COLLAPSED_UNIFORM": {}, "COLLAPSED_DELTA": {}}}
        }),
        ("frozen_false", {
            "schema_version": "v1",
            "frozen": False,
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {"collapse_detection": {"HEALTHY": {}, "COLLAPSED_UNIFORM": {}, "COLLAPSED_DELTA": {}}}
        }),
        ("negative_threshold", {
            "schema_version": "v1",
            "frozen": True,
            "frozen_at_utc": "2026-01-15T00:00:00Z",
            "thresholds": {
                "collapse_detection": {
                    "HEALTHY": {"entropy_min": -0.1, "gini_max": 0.6},
                    "COLLAPSED_UNIFORM": {"entropy_max": 0.2, "gini_max": 0.4},
                    "COLLAPSED_DELTA": {"entropy_min": 0.8, "gini_min": 0.8}
                }
            }
        }),
    ]
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        scores = [5.0, 4.0, 3.0, 2.0, 1.0]
        
        for case_name, file_content in test_cases:
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
        
        print("PASS: enforce never fail-open (frozen)")
    finally:
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
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
        test_enforce_missing_frozen_thresholds_file,
        test_enforce_frozen_field_missing,
        test_enforce_frozen_false,
        test_enforce_valid_frozen_file,
        test_fingerprint_stable,
        test_enforce_frozen_schema_invalid,
        test_enforce_never_fail_open_frozen,
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

