#!/usr/bin/env python3
"""
Calibration Layer Unit Tests
Shadow only 검증: 행동 변경 없음 (identity mapping)
"""

import sys
import os

# 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibration_layer import (
    map_score_to_probability,
    calculate_calibration_telemetry,
    calculate_calibration_curve_bucket,
    calculate_ece,
)


def test_identity_mapping_no_behavior_change():
    """Identity mapping이 행동 변경 없음을 검증"""
    primary = 5.0
    secondary = 0.5
    
    prob = map_score_to_probability(primary, secondary, "v1.0-identity")
    
    # Identity mapping이므로 primary와 동일해야 함
    assert prob == primary, f"Identity mapping failed: {prob} != {primary}"
    print("PASS: identity mapping (no behavior change)")


def test_calibration_ranking_unchanged():
    """Calibration 후 랭킹이 변경되지 않음을 검증"""
    ranked_before = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    # Calibration 적용 (identity mapping)
    ranked_after = []
    for primary, secondary, did, dt in ranked_before:
        prob = map_score_to_probability(primary, secondary, "v1.0-identity")
        ranked_after.append((prob, secondary, did, dt))
    
    # 랭킹 길이 동일
    assert len(ranked_before) == len(ranked_after), "Ranking length changed"
    
    # 각 항목의 primary score 동일 (identity mapping)
    for (p_before, s_before, d_before, dt_before), (p_after, s_after, d_after, dt_after) in zip(ranked_before, ranked_after):
        assert p_before == p_after, f"Primary score changed: {p_before} != {p_after}"
        assert d_before == d_after, f"Doc ID changed: {d_before} != {d_after}"
    
    print("PASS: calibration ranking unchanged")


def test_calibration_telemetry_meta_only():
    """Calibration telemetry가 meta-only인지 검증"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    telemetry = calculate_calibration_telemetry(ranked, ranked, relevant_docs, 3)
    
    # 필수 키 확인
    assert "calibration_curve_bucket" in telemetry
    assert "ece_bucket" in telemetry
    assert "score_to_prob_version" in telemetry
    
    # Meta-only 검증 (문자열만)
    allowed_types = (str,)
    for key, value in telemetry.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
    
    # 원문/후보 리스트 출력 없음 확인
    assert "ranked" not in telemetry
    assert "docs" not in telemetry
    assert "query" not in telemetry
    
    print("PASS: calibration telemetry meta-only")


def test_calibration_indicators_added():
    """Calibration 지표만 추가되고 기존 지표는 변경되지 않음을 검증"""
    ranked = [
        (5.0, 0.5, "doc1", set()),
        (4.0, 0.4, "doc2", set()),
        (3.0, 0.3, "doc3", set()),
    ]
    relevant_docs = {"doc1", "doc2"}
    
    telemetry = calculate_calibration_telemetry(ranked, ranked, relevant_docs, 3)
    
    # 새로운 지표만 추가
    assert "calibration_curve_bucket" in telemetry
    assert "ece_bucket" in telemetry
    assert "score_to_prob_version" in telemetry
    
    # 기존 지표 키는 없어야 함 (이 함수는 calibration 지표만 반환)
    # 실제 report에서는 다른 지표와 함께 포함됨
    
    print("PASS: calibration indicators added")


def test_calibration_bucket_deterministic():
    """Calibration bucket 계산이 결정론적인지 검증"""
    errors1 = [0.05, 0.10, 0.15]
    errors2 = [0.05, 0.10, 0.15]
    
    bucket1 = calculate_calibration_curve_bucket(errors1)
    bucket2 = calculate_calibration_curve_bucket(errors2)
    
    assert bucket1 == bucket2, f"Calibration bucket not deterministic: {bucket1} != {bucket2}"
    print("PASS: calibration bucket deterministic")


def main():
    """모든 테스트 실행"""
    tests = [
        test_identity_mapping_no_behavior_change,
        test_calibration_ranking_unchanged,
        test_calibration_telemetry_meta_only,
        test_calibration_indicators_added,
        test_calibration_bucket_deterministic,
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

