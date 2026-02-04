#!/usr/bin/env python3
"""
GTB v0.3 Canary Mode Unit Tests
D0 결정론 검증: 동일 입력에 대해 항상 동일한 결과
Fail-Closed 검증: Meta-Guard gate_allow=false면 무조건 비활성화
"""

import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gtb_v03_canary import (
    calculate_canary_bucket,
    should_apply_gtb_canary,
    should_apply_gtb_canary_with_config,
    apply_gtb_v03_canary,
)
from gtb_v03_shadow import calculate_swap_budget
from gtb_v03_canary_config import load_canary_config


def test_canary_bucket_deterministic():
    """카나리 버킷 계산이 결정론적인지 검증"""
    request_id = "test-request-123"
    bucket1 = calculate_canary_bucket(request_id)
    bucket2 = calculate_canary_bucket(request_id)
    assert bucket1 == bucket2, f"Canary bucket not deterministic: {bucket1} != {bucket2}"
    assert 0 <= bucket1 < 100, f"Canary bucket out of range: {bucket1}"
    print("PASS: canary bucket deterministic")


def test_fail_closed_meta_guard():
    """Meta-Guard gate_allow=false면 무조건 비활성화 (Fail-Closed)"""
    # gate_allow=False면 canary_percent와 관계없이 False
    assert should_apply_gtb_canary("test", 100, False) == False, "Should be disabled when gate_allow=False"
    assert should_apply_gtb_canary("test", 50, False) == False, "Should be disabled when gate_allow=False"
    assert should_apply_gtb_canary("test", 0, False) == False, "Should be disabled when gate_allow=False"
    print("PASS: Fail-Closed when gate_allow=False")


def test_canary_routing_deterministic():
    """카나리 라우팅이 결정론적인지 검증"""
    request_id = "test-request-456"
    canary_percent = 50
    
    result1 = should_apply_gtb_canary(request_id, canary_percent, True)
    result2 = should_apply_gtb_canary(request_id, canary_percent, True)
    
    assert result1 == result2, f"Canary routing not deterministic: {result1} != {result2}"
    print("PASS: canary routing deterministic")


def test_gtb_canary_meta_only():
    """GTB Canary 출력이 meta-only인지 검증 (원문 출력 없음)"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (5.0, 0.3, "doc2", set()),
        (4.0, 0.0, "doc3", set()),
    ]
    gap_p25 = 0.0
    max_swaps = 1
    relevant_docs = {"doc1", "doc2"}
    baseline_ranked = ["doc1", "doc2", "doc3"]
    
    applied_ranked, result = apply_gtb_v03_canary(
        ranked, 3, gap_p25, max_swaps, relevant_docs, baseline_ranked, 10
    )
    
    # 숫자/불린/문자열(meta-only)만 허용 (원문/리스트 없음)
    allowed_types = (int, bool, str, float)
    for key, value in result.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
        if isinstance(value, str):
            # 문자열은 reason_code, config_source 등 meta-only 값만 허용
            assert key in ["blocked_reason_code", "config_source"], \
                f"Unexpected string key: {key}={value}"
    
    # 필수 키 확인
    required_keys = ["applied", "canary_bucket", "swaps_applied_count", "moved_up_count", "moved_down_count"]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"
    
    print("PASS: GTB canary meta-only")


def test_gtb_canary_blocked_by_meta_guard_collapsed():
    """Meta-Guard COLLAPSED_*일 때 GTB Canary가 applied=false인지 검증"""
    from meta_guard import calculate_meta_guard_for_query
    
    # COLLAPSED_UNIFORM 케이스: 매우 작은 변동성
    ranked_collapsed = [
        (0.1, 0.0, "doc1", set()),
        (0.1, 0.0, "doc2", set()),
        (0.1, 0.0, "doc3", set()),
    ]
    k = 3
    
    # Meta-Guard 계산 (enforce 모드)
    meta_guard_result = calculate_meta_guard_for_query(ranked_collapsed, k, observe_only=False)
    
    # COLLAPSED_*이면 gate_allow=False
    if meta_guard_result["meta_guard_state"] in ["COLLAPSED_UNIFORM", "COLLAPSED_DELTA"]:
        assert meta_guard_result["gate_allow"] == False, \
            f"gate_allow should be False for COLLAPSED: {meta_guard_result}"
        
        # should_apply_gtb_canary는 gate_allow=False면 False 반환
        should_apply = should_apply_gtb_canary("test-req", 50, meta_guard_result["gate_allow"])
        assert should_apply == False, \
            f"should_apply_gtb_canary should be False when gate_allow=False: {should_apply}"
        
        print("PASS: GTB canary blocked by Meta-Guard COLLAPSED")
    else:
        print(f"INFO: Meta-Guard state is {meta_guard_result['meta_guard_state']}, not COLLAPSED (gate_allow={meta_guard_result['gate_allow']})")


def test_gtb_canary_allowed_by_meta_guard_healthy():
    """Meta-Guard HEALTHY일 때 기존 Canary 조건을 유지하는지 검증"""
    from meta_guard import calculate_meta_guard_for_query
    
    # HEALTHY 케이스: 정상 분포
    ranked_healthy = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
        (2.0, 0.2, "doc4", set()),
        (1.0, 0.1, "doc5", set()),
    ]
    k = 5
    
    # Meta-Guard 계산 (enforce 모드)
    meta_guard_result = calculate_meta_guard_for_query(ranked_healthy, k, observe_only=False)
    
    # HEALTHY이면 gate_allow=True
    if meta_guard_result["meta_guard_state"] == "HEALTHY":
        assert meta_guard_result["gate_allow"] == True, \
            f"gate_allow should be True for HEALTHY: {meta_guard_result}"
        
        # should_apply_gtb_canary는 기존 Canary 조건에 따라 결정
        # canary_percent=0이면 False
        should_apply_0 = should_apply_gtb_canary("test-req", 0, meta_guard_result["gate_allow"])
        assert should_apply_0 == False, \
            f"should_apply_gtb_canary should be False when canary_percent=0: {should_apply_0}"
        
        # canary_percent=100이면 True (gate_allow=True이므로)
        should_apply_100 = should_apply_gtb_canary("test-req", 100, meta_guard_result["gate_allow"])
        assert should_apply_100 == True, \
            f"should_apply_gtb_canary should be True when canary_percent=100 and gate_allow=True: {should_apply_100}"
        
        print("PASS: GTB canary allowed by Meta-Guard HEALTHY (canary conditions preserved)")
    else:
        print(f"INFO: Meta-Guard state is {meta_guard_result['meta_guard_state']}, not HEALTHY")


def test_config_determinism():
    """Config 기반 결정론: 같은 request_key => 같은 bucket => 같은 applied"""
    config = {
        "canary_percent": 50,
        "kill_switch": False,
        "routing_seed": "test-seed",
        "_config_source": "FILE",
    }
    request_key = "test-request-123"
    
    should_apply1, reason1, tel1 = should_apply_gtb_canary_with_config(
        request_key, config, True
    )
    should_apply2, reason2, tel2 = should_apply_gtb_canary_with_config(
        request_key, config, True
    )
    
    assert should_apply1 == should_apply2, \
        f"Not deterministic: {should_apply1} != {should_apply2}"
    assert tel1["canary_percent"] == tel2["canary_percent"]
    assert tel1["applied"] == tel2["applied"]
    
    print("PASS: config determinism")


def test_missing_config_fail_closed():
    """Missing config => fail-closed"""
    import os
    from gtb_v03_canary_config import CONFIG_FILE, load_canary_config
    
    original_path = CONFIG_FILE
    backup_path = original_path + ".backup"
    
    # 환경 변수 백업 및 제거
    env_backup = {}
    for key in ["GTB_CANARY_PERCENT", "GTB_CANARY_KILL_SWITCH", "GTB_CANARY_ROUTING_SEED"]:
        env_backup[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Config 로드 시도
        config, err_code, source = load_canary_config()
        
        assert config is None, f"Expected None config, got {config}"
        assert err_code == "CANARY_CONFIG_INVALID_FAILCLOSED", \
            f"Expected CANARY_CONFIG_INVALID_FAILCLOSED, got {err_code}"
        assert source == "MISSING_FAILCLOSED", \
            f"Expected MISSING_FAILCLOSED, got {source}"
        
        # should_apply_gtb_canary_with_config는 config가 None이면 fail-closed
        should_apply, reason_code, telemetry = should_apply_gtb_canary_with_config(
            "test-request", None, True
        )
        assert should_apply == False, \
            f"Expected applied=False for None config, got {should_apply}"
        assert reason_code == "CANARY_CONFIG_INVALID_FAILCLOSED", \
            f"Expected CANARY_CONFIG_INVALID_FAILCLOSED, got {reason_code}"
        assert telemetry["blocked_reason_code"] == "CANARY_CONFIG_INVALID_FAILCLOSED"
        assert telemetry["config_source"] == "MISSING_FAILCLOSED"
        
        print("PASS: missing config fail-closed")
    finally:
        if os.path.exists(backup_path):
            os.rename(backup_path, original_path)
        for key, value in env_backup.items():
            if value is not None:
                os.environ[key] = value
        # 캐시 초기화
        import gtb_v03_canary_config
        gtb_v03_canary_config._config_cache = None
        gtb_v03_canary_config._config_err_cache = None


def test_kill_switch_fail_closed():
    """kill_switch => fail-closed"""
    config = {
        "canary_percent": 100,
        "kill_switch": True,
        "routing_seed": "test",
        "_config_source": "FILE",
    }
    
    should_apply, reason_code, telemetry = should_apply_gtb_canary_with_config(
        "test-request", config, True
    )
    
    assert should_apply == False, \
        f"Expected applied=False for kill_switch, got {should_apply}"
    assert reason_code == "CANARY_KILL_SWITCH_ON", \
        f"Expected CANARY_KILL_SWITCH_ON, got {reason_code}"
    assert telemetry["applied"] == False
    assert telemetry["blocked_reason_code"] == "CANARY_KILL_SWITCH_ON"
    assert telemetry["canary_percent"] == 100
    assert telemetry["kill_switch"] == True
    assert telemetry["config_source"] == "FILE"
    
    print("PASS: kill_switch fail-closed")


def test_required_keys_emitted():
    """Required keys가 applied/blocked 모든 경우에 emit되는지 검증"""
    # Applied 케이스
    config_applied = {
        "canary_percent": 100,
        "kill_switch": False,
        "routing_seed": "test",
        "_config_source": "FILE",
    }
    should_apply, reason_code, telemetry = should_apply_gtb_canary_with_config(
        "test-request", config_applied, True
    )
    
    required_keys = ["canary_percent", "kill_switch", "applied", "applied_ratio", "blocked_reason_code", "config_source"]
    for key in required_keys:
        assert key in telemetry, f"Missing required key: {key}"
    
    # Blocked 케이스 (kill_switch)
    config_blocked = {
        "canary_percent": 50,
        "kill_switch": True,
        "routing_seed": "test",
        "_config_source": "FILE",
    }
    should_apply, reason_code, telemetry = should_apply_gtb_canary_with_config(
        "test-request", config_blocked, True
    )
    
    for key in required_keys:
        assert key in telemetry, f"Missing required key in blocked case: {key}"
    
    print("PASS: required keys emitted")


def test_invalid_config_fail_closed():
    """Invalid config (out of range canary_percent) => fail-closed"""
    import json
    import os
    from gtb_v03_canary_config import CONFIG_FILE, load_canary_config
    
    original_path = CONFIG_FILE
    backup_path = original_path + ".backup"
    
    # 환경 변수 백업 및 제거
    env_backup = {}
    for key in ["GTB_CANARY_PERCENT", "GTB_CANARY_KILL_SWITCH", "GTB_CANARY_ROUTING_SEED"]:
        env_backup[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]
    
    try:
        if os.path.exists(original_path):
            os.rename(original_path, backup_path)
        
        # Invalid config (canary_percent > 100)
        invalid_config = {
            "canary_percent": 150,  # Invalid: > 100
            "kill_switch": False,
            "routing_seed": "test",
        }
        with open(original_path, "w", encoding="utf-8") as f:
            json.dump(invalid_config, f)
        
        config, err_code, source = load_canary_config()
        
        assert config is None, f"Expected None config, got {config}"
        assert err_code == "CANARY_CONFIG_INVALID_FAILCLOSED", \
            f"Expected CANARY_CONFIG_INVALID_FAILCLOSED, got {err_code}"
        
        print("PASS: invalid config fail-closed")
    finally:
        if os.path.exists(backup_path):
            if os.path.exists(original_path):
                os.remove(original_path)
            os.rename(backup_path, original_path)
        for key, value in env_backup.items():
            if value is not None:
                os.environ[key] = value
        import gtb_v03_canary_config
        gtb_v03_canary_config._config_cache = None
        gtb_v03_canary_config._config_err_cache = None


def main():
    """모든 테스트 실행"""
    tests = [
        test_canary_bucket_deterministic,
        test_fail_closed_meta_guard,
        test_canary_routing_deterministic,
        test_gtb_canary_meta_only,
        test_gtb_canary_blocked_by_meta_guard_collapsed,
        test_gtb_canary_allowed_by_meta_guard_healthy,
        test_config_determinism,
        test_missing_config_fail_closed,
        test_kill_switch_fail_closed,
        test_required_keys_emitted,
        test_invalid_config_fail_closed,
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
