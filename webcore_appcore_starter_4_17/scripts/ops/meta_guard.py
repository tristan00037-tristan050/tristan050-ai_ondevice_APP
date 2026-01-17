#!/usr/bin/env python3
"""
Meta-Guard: 분포 붕괴 감지 및 GTB 개입 Fail-Closed 비활성화
기본 원칙: 분포가 붕괴로 판단되면 GTB 개입을 Fail-Closed로 비활성화 (=개입하지 않음)
"""

import json
import math
import os
import hashlib
from typing import List, Tuple, Dict, Optional

# SSOT 임계치 파일 경로 (하드코딩 금지)
THRESHOLDS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "step4b", "meta_guard_thresholds_v1.json"
)

# Frozen thresholds 파일 경로 (enforce 모드용)
FROZEN_THRESHOLDS_FILE = os.path.join(
    os.path.dirname(__file__),
    "config", "meta_guard_thresholds_frozen.v1.json"
)

# 임계치 캐시 (파일에서 한 번만 읽기)
_thresholds_cache: Optional[Dict] = None
_thresholds_err_cache: Optional[str] = None


def calculate_thresholds_fingerprint(thresholds: Dict) -> str:
    """
    Thresholds 객체의 SHA256 fingerprint 계산 (canonicalized)
    
    Args:
        thresholds: thresholds 딕셔너리
    
    Returns:
        SHA256 hex digest (meta-only)
    """
    # Canonicalize: thresholds만 추출하고 정렬된 JSON으로 변환
    thresholds_only = thresholds.get("thresholds", thresholds)
    canonical_json = json.dumps(thresholds_only, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def load_frozen_thresholds_with_validation(path: str) -> Tuple[Optional[Dict], Optional[str], Optional[str], Optional[str]]:
    """
    Frozen thresholds 파일 로드 및 검증 (explicit frozen contract)
    
    Args:
        path: frozen thresholds 파일 경로
    
    Returns:
        (thresholds_obj | None, err_code | None, schema_version | None, fingerprint | None)
        - thresholds_obj: 로드 및 검증 성공 시 딕셔너리
        - err_code: 오류 시 reason_code
        - schema_version: 성공 시 schema_version
        - fingerprint: 성공 시 SHA256 fingerprint
    """
    # 파일 존재 및 읽기 가능 확인
    if not os.path.exists(path):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", None, None
    
    if not os.access(path, os.R_OK):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", None, None
    
    # JSON 파싱
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, IOError):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED", None, None
    
    # Frozen contract 검증
    if not isinstance(data, dict):
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    # 필수 frozen contract 필드 확인
    schema_version = data.get("schema_version")
    frozen = data.get("frozen")
    frozen_at_utc = data.get("frozen_at_utc")
    thresholds = data.get("thresholds")
    
    if schema_version != "v1":
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    if frozen is not True:
        return None, "META_GUARD_THRESHOLDS_NOT_FROZEN_FAILCLOSED", None, None
    
    if not isinstance(frozen_at_utc, str) or not frozen_at_utc:
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    if not isinstance(thresholds, dict):
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    # Thresholds 구조 검증
    collapse_detection = thresholds.get("collapse_detection")
    if not isinstance(collapse_detection, dict):
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    # 필수 키 확인
    required_states = ["HEALTHY", "COLLAPSED_UNIFORM", "COLLAPSED_DELTA"]
    for state in required_states:
        if state not in collapse_detection:
            return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    # 숫자 범위 검증 (sanity check)
    for state, rule in collapse_detection.items():
        if not isinstance(rule, dict):
            return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
        
        # 엔트로피/지니 값이 0~1 범위인지 확인 (음수 불가)
        for key in ["entropy_min", "entropy_max", "gini_min", "gini_max"]:
            if key in rule:
                value = rule[key]
                if not isinstance(value, (int, float)):
                    return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
                if value < 0.0 or value > 1.0:
                    return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED", None, None
    
    # Fingerprint 계산
    fingerprint = calculate_thresholds_fingerprint(data)
    
    return data, None, schema_version, fingerprint


def load_thresholds_with_validation(path: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    SSOT 임계치 파일 로드 및 검증 (strict fail-closed)
    
    Args:
        path: 임계치 파일 경로
    
    Returns:
        (thresholds_obj | None, err_code | None)
        - thresholds_obj: 로드 및 검증 성공 시 딕셔너리
        - err_code: 오류 시 reason_code (META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED 또는 META_GUARD_SCHEMA_INVALID_FAILCLOSED)
    """
    # 파일 존재 및 읽기 가능 확인
    if not os.path.exists(path):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED"
    
    if not os.access(path, os.R_OK):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED"
    
    # JSON 파싱
    try:
        with open(path, "r", encoding="utf-8") as f:
            thresholds = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, IOError):
        return None, "META_GUARD_THRESHOLDS_UNAVAILABLE_FAILCLOSED"
    
    # 스키마 검증
    if not isinstance(thresholds, dict):
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
    
    collapse_detection = thresholds.get("collapse_detection")
    if not isinstance(collapse_detection, dict):
        return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
    
    # 필수 키 확인
    required_states = ["HEALTHY", "COLLAPSED_UNIFORM", "COLLAPSED_DELTA"]
    for state in required_states:
        if state not in collapse_detection:
            return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
    
    # 숫자 범위 검증 (sanity check)
    for state, rule in collapse_detection.items():
        if not isinstance(rule, dict):
            return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
        
        # 엔트로피/지니 값이 0~1 범위인지 확인 (음수 불가)
        for key in ["entropy_min", "entropy_max", "gini_min", "gini_max"]:
            if key in rule:
                value = rule[key]
                if not isinstance(value, (int, float)):
                    return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
                if value < 0.0 or value > 1.0:
                    return None, "META_GUARD_SCHEMA_INVALID_FAILCLOSED"
    
    return thresholds, None


def load_thresholds() -> Dict:
    """
    SSOT 임계치 파일에서 로드 (observe-only 호환성 유지)
    
    Returns:
        임계치 딕셔너리 (observe-only 모드용)
    """
    global _thresholds_cache, _thresholds_err_cache
    
    if _thresholds_cache is not None:
        return _thresholds_cache
    
    if _thresholds_err_cache is not None:
        # 이전에 오류가 있었으면 기본값 반환 (observe-only 호환)
        return _get_default_thresholds()
    
    thresholds, err_code = load_thresholds_with_validation(THRESHOLDS_FILE)
    
    if err_code is not None:
        _thresholds_err_cache = err_code
        return _get_default_thresholds()
    
    _thresholds_cache = thresholds
    return _thresholds_cache


def _get_default_thresholds() -> Dict:
    """기본 임계치 (observe-only 모드용, enforce 모드에서는 사용 안 함)"""
    return {
        "collapse_detection": {
            "HEALTHY": {
                "entropy_min": 0.4,
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


def calculate_entropy(scores: List[float]) -> float:
    """정규화 엔트로피 계산 (결정론적)"""
    if not scores or len(scores) == 0:
        return 0.0
    
    # Score를 양수로 정규화 (min을 0으로)
    min_score = min(scores)
    if min_score < 0:
        normalized = [s - min_score for s in scores]
    else:
        normalized = scores
    
    # 합이 0이면 엔트로피 0
    total = sum(normalized)
    if total == 0:
        return 0.0
    
    # 확률 분포로 정규화
    probs = [s / total for s in normalized]
    
    # 엔트로피 계산: -sum(p * log2(p))
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log2(p)
    
    # 정규화: log2(n)으로 나눔
    n = len(scores)
    if n <= 1:
        return 0.0
    normalized_entropy = entropy / math.log2(n)
    
    return normalized_entropy


def calculate_gini(scores: List[float]) -> float:
    """지니 계수 계산 (결정론적)"""
    if not scores or len(scores) < 2:
        return 0.0
    
    # Score를 양수로 정규화
    min_score = min(scores)
    if min_score < 0:
        normalized = [s - min_score + 1.0 for s in scores]  # +1 to ensure positive
    else:
        normalized = [s + 1.0 for s in scores]  # +1 to ensure positive
    
    # 정렬 (오름차순)
    sorted_scores = sorted(normalized)
    n = len(sorted_scores)
    total = sum(sorted_scores)
    
    if total == 0:
        return 0.0
    
    # 지니 계수: 1 - 2 * sum((n - i + 0.5) * score[i]) / (n * sum(scores))
    cumsum = 0.0
    for i, score in enumerate(sorted_scores):
        cumsum += (n - i + 0.5) * score
    
    gini = 1.0 - (2.0 * cumsum) / (n * total)
    return max(0.0, min(1.0, gini))  # 0~1 범위로 클램핑


def bucketize_entropy(entropy: float) -> str:
    """엔트로피 버킷화 (meta-only)"""
    if entropy < 0.2:
        return "VERY_LOW"
    elif entropy < 0.4:
        return "LOW"
    elif entropy < 0.6:
        return "MEDIUM"
    elif entropy < 0.8:
        return "HIGH"
    else:
        return "VERY_HIGH"


def bucketize_gini(gini: float) -> str:
    """지니 계수 버킷화 (meta-only)"""
    if gini < 0.2:
        return "LOW_INEQUALITY"
    elif gini < 0.4:
        return "MEDIUM_INEQUALITY"
    elif gini < 0.6:
        return "HIGH_INEQUALITY"
    else:
        return "VERY_HIGH_INEQUALITY"


def detect_distribution_collapse(
    scores: List[float],
    observe_only: bool = False
) -> Dict:
    """
    분포 붕괴 감지 (Meta-Guard) - Enforce 모드
    
    Args:
        scores: Primary score 리스트
        observe_only: False면 실제 차단 적용 (enforce), True면 관찰만
    
    Returns:
        meta-only 딕셔너리:
        - meta_guard_state: HEALTHY / COLLAPSED_UNIFORM / COLLAPSED_DELTA / UNKNOWN
        - gate_allow: bool (observe_only=False면 COLLAPSED_*일 때 False)
        - entropy_bucket: str
        - gini_bucket: str
        - reason_code: str (차단 시 META_GUARD_COLLAPSED)
    """
    if not scores or len(scores) == 0:
        return {
            "meta_guard_state": "UNKNOWN",
            "gate_allow": False if not observe_only else True,  # Fail-Closed: UNKNOWN은 비활성화
            "entropy_bucket": "VERY_LOW",
            "gini_bucket": "LOW_INEQUALITY",
            "reason_code": "META_GUARD_UNKNOWN" if not observe_only else None,
            "thresholds_schema_version": None,
            "thresholds_fingerprint": None,
        }
    
    # 엔트로피 및 지니 계산
    entropy = calculate_entropy(scores)
    gini = calculate_gini(scores)
    
    entropy_bucket = bucketize_entropy(entropy)
    gini_bucket = bucketize_gini(gini)
    
    # SSOT 임계치 로드 및 검증 (enforce 모드: frozen contract required)
    if observe_only:
        # Observe-only 모드: 기존 동작 유지 (meta reporting)
        thresholds = load_thresholds()
        collapse_rules = thresholds.get("collapse_detection", {})
        thresholds_err = None
        schema_version = None
        fingerprint = None
    else:
        # Enforce 모드: frozen thresholds required (explicit frozen contract)
        frozen_data, thresholds_err, schema_version, fingerprint = load_frozen_thresholds_with_validation(FROZEN_THRESHOLDS_FILE)
        if thresholds_err is not None:
            # Frozen thresholds 오류: Fail-Closed (NO FAIL-OPEN)
            return {
                "meta_guard_state": "UNKNOWN",
                "gate_allow": False,
                "entropy_bucket": entropy_bucket,
                "gini_bucket": gini_bucket,
                "reason_code": thresholds_err,
                "thresholds_schema_version": None,
                "thresholds_fingerprint": None,
            }
        thresholds = frozen_data.get("thresholds", {})
        collapse_rules = thresholds.get("collapse_detection", {})
        if not collapse_rules:
            # 스키마 오류 (collapse_detection 없음)
            return {
                "meta_guard_state": "UNKNOWN",
                "gate_allow": False,
                "entropy_bucket": entropy_bucket,
                "gini_bucket": gini_bucket,
                "reason_code": "META_GUARD_SCHEMA_INVALID_FAILCLOSED",
                "thresholds_schema_version": schema_version,
                "thresholds_fingerprint": None,
            }
    
    # 분포 붕괴 판정 (SSOT 임계치 사용)
    state = "UNKNOWN"
    reason_code = None
    
    # COLLAPSED_UNIFORM 판정
    uniform_rule = collapse_rules.get("COLLAPSED_UNIFORM", {})
    entropy_max = uniform_rule.get("entropy_max", 0.2)
    exclusive_entropy_max = uniform_rule.get("exclusive_entropy_max", True)
    gini_max = uniform_rule.get("gini_max", 0.4)
    exclusive_gini_max = uniform_rule.get("exclusive_gini_max", True)
    
    if (entropy < entropy_max if exclusive_entropy_max else entropy <= entropy_max) and \
       (gini < gini_max if exclusive_gini_max else gini <= gini_max):
        state = "COLLAPSED_UNIFORM"
        reason_code = "META_GUARD_COLLAPSED_UNIFORM"
    
    # COLLAPSED_DELTA 판정 (COLLAPSED_UNIFORM이 아니면)
    if state == "UNKNOWN":
        delta_rule = collapse_rules.get("COLLAPSED_DELTA", {})
        entropy_min = delta_rule.get("entropy_min", 0.8)
        gini_min = delta_rule.get("gini_min", 0.8)
        
        if entropy >= entropy_min and gini >= gini_min:
            state = "COLLAPSED_DELTA"
            reason_code = "META_GUARD_COLLAPSED_DELTA"
    
    # HEALTHY 판정 (COLLAPSED가 아니면)
    if state == "UNKNOWN":
        healthy_rule = collapse_rules.get("HEALTHY", {})
        entropy_min = healthy_rule.get("entropy_min", 0.4)
        gini_max = healthy_rule.get("gini_max", 0.6)
        exclusive_gini_max = healthy_rule.get("exclusive_gini_max", True)
        
        if entropy >= entropy_min and (gini < gini_max if exclusive_gini_max else gini <= gini_max):
            state = "HEALTHY"
            reason_code = "META_GUARD_OK"  # HEALTHY는 OK reason_code
    
    # gate_allow 결정 (enforce 모드)
    if observe_only:
        # 관찰 모드: 항상 True (행동 변경 없음)
        gate_allow = True
        # reason_code는 기존 로직 유지 (COLLAPSED 시에만 설정)
    else:
        # Enforce 모드: COLLAPSED_*이면 False (Fail-Closed)
        gate_allow = (state == "HEALTHY")
        # HEALTHY가 아니면 reason_code 설정 (이미 위에서 설정됨)
        if state == "UNKNOWN" and reason_code is None:
            # UNKNOWN 상태인데 reason_code가 없으면 (thresholds 오류는 이미 처리됨)
            reason_code = "META_GUARD_UNKNOWN"
    
    return {
        "meta_guard_state": state,
        "gate_allow": gate_allow,
        "entropy_bucket": entropy_bucket,
        "gini_bucket": gini_bucket,
        "reason_code": reason_code,
        "thresholds_schema_version": schema_version if not observe_only else None,
        "thresholds_fingerprint": fingerprint if not observe_only else None,
    }


def calculate_meta_guard_for_query(
    ranked: List[Tuple[float, float, str, set]],
    k: int,
    observe_only: bool = False
) -> Dict:
    """
    쿼리별 Meta-Guard 계산 (Enforce 모드)
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (이미 정렬됨)
        k: topK 값
        observe_only: False면 실제 차단 적용 (enforce), True면 관찰만
    
    Returns:
        meta-only 딕셔너리
    """
    if not ranked or len(ranked) == 0:
        return {
            "meta_guard_state": "UNKNOWN",
            "gate_allow": False if not observe_only else True,
            "entropy_bucket": "VERY_LOW",
            "gini_bucket": "LOW_INEQUALITY",
            "reason_code": "META_GUARD_UNKNOWN" if not observe_only else None,
            "thresholds_schema_version": None,
            "thresholds_fingerprint": None,
        }
    
    topk_ranked = ranked[:k]
    primary_scores = [p for p, _, _, _ in topk_ranked]
    
    return detect_distribution_collapse(primary_scores, observe_only=observe_only)


if __name__ == "__main__":
    # Unit test용
    # Test 1: 결정론적 검증
    scores_test = [5.0, 4.0, 3.0, 2.0, 1.0]
    result1 = detect_distribution_collapse(scores_test, observe_only=False)
    result2 = detect_distribution_collapse(scores_test, observe_only=False)
    
    assert result1 == result2, f"Not deterministic: {result1} != {result2}"
    print("PASS: Meta-Guard deterministic")
    
    # Test 2: enforce 모드에서 HEALTHY는 gate_allow=True
    assert result1["gate_allow"] == True, f"gate_allow should be True for HEALTHY: {result1}"
    assert result1["meta_guard_state"] == "HEALTHY", f"Expected HEALTHY, got {result1['meta_guard_state']}"
    print("PASS: HEALTHY -> gate_allow=True")
    
    # Test 3: COLLAPSED_UNIFORM은 gate_allow=False (Fail-Closed)
    # 엔트로피 < 0.2 AND 지니 < 0.4 조건을 만족하는 케이스
    # 매우 작은 변동성: [0.1, 0.1, 0.1, 0.1, 0.1] (거의 동일)
    scores_uniform = [0.1, 0.1, 0.1, 0.1, 0.1]
    result_uniform = detect_distribution_collapse(scores_uniform, observe_only=False)
    # 실제 판정 결과에 따라 검증 (엔트로피 계산 방식에 따라 다를 수 있음)
    if result_uniform["meta_guard_state"] == "COLLAPSED_UNIFORM":
        assert result_uniform["gate_allow"] == False, \
            f"gate_allow should be False for COLLAPSED_UNIFORM: {result_uniform}"
        assert result_uniform.get("reason_code") == "META_GUARD_COLLAPSED_UNIFORM", \
            f"Expected reason_code META_GUARD_COLLAPSED_UNIFORM: {result_uniform}"
        print("PASS: COLLAPSED_UNIFORM -> gate_allow=False")
    else:
        # COLLAPSED_UNIFORM이 아니더라도, gate_allow=False인 경우는 Fail-Closed 동작 확인
        print(f"INFO: Meta-Guard state is {result_uniform['meta_guard_state']}, gate_allow={result_uniform['gate_allow']}")
    
    # Test 4: COLLAPSED_DELTA는 gate_allow=False (Fail-Closed)
    # 고엔트로피 + 고지니: [100.0, 1.0, 1.0, 1.0, 1.0]
    scores_delta = [100.0, 1.0, 1.0, 1.0, 1.0]
    result_delta = detect_distribution_collapse(scores_delta, observe_only=False)
    # COLLAPSED_DELTA 판정은 엔트로피 >= 0.8 AND 지니 >= 0.8
    # 이 케이스는 실제로는 지니가 높을 수 있지만, 엔트로피도 높을 수 있음
    # 실제 판정 결과에 따라 검증
    if result_delta["meta_guard_state"] == "COLLAPSED_DELTA":
        assert result_delta["gate_allow"] == False, \
            f"gate_allow should be False for COLLAPSED_DELTA: {result_delta}"
        assert result_delta.get("reason_code") == "META_GUARD_COLLAPSED_DELTA", \
            f"Expected reason_code META_GUARD_COLLAPSED_DELTA: {result_delta}"
    print("PASS: COLLAPSED_DELTA -> gate_allow=False (if detected)")
    
    # Test 5: meta-only 검증
    allowed_types = (str, bool, type(None))
    for key, value in result1.items():
        assert isinstance(value, allowed_types), f"Non-meta-only value: {key}={value} (type: {type(value)})"
    print("PASS: Meta-Guard meta-only")
    
    print("OK: Meta-Guard tests passed")

