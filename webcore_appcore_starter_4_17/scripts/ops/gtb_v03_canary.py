#!/usr/bin/env python3
"""
GTB v0.3 Canary Mode (결정론적, Fail-Closed)
카나리 라우팅 + Meta-Guard gate_allow로 GTB를 제한적으로만 적용
"""

import hashlib
import math
from typing import List, Tuple, Dict, Set


def calculate_canary_bucket(request_id: str) -> int:
    """
    카나리 버킷 계산 (결정론적 D0)
    request_id 해시 mod 100으로 0~99 버킷 반환
    """
    if not request_id:
        return 0
    
    # SHA256 해시 (결정론적)
    hash_bytes = hashlib.sha256(request_id.encode('utf-8')).digest()
    # 첫 8바이트를 정수로 변환
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    # mod 100으로 0~99 버킷
    bucket = hash_int % 100
    return bucket


def should_apply_gtb_canary(
    request_id: str,
    canary_percent: int,
    meta_guard_gate_allow: bool
) -> bool:
    """
    카나리 모드에서 GTB 적용 여부 결정 (Fail-Closed)
    
    Args:
        request_id: 요청 ID (결정론적 라우팅용)
        canary_percent: 카나리 비율 (0~100)
        meta_guard_gate_allow: Meta-Guard gate_allow 값
    
    Returns:
        True면 GTB 적용, False면 비활성화
    """
    # Fail-Closed: Meta-Guard gate_allow=false면 무조건 비활성화
    if not meta_guard_gate_allow:
        return False
    
    # 카나리 라우팅: request_id 해시 mod 100 < canary_percent
    bucket = calculate_canary_bucket(request_id)
    return bucket < canary_percent


def apply_gtb_v03_canary(
    ranked: List[Tuple[float, float, str, set]],
    k: int,
    gap_p25: float,
    max_swaps: int,
    relevant_docs: Set[str],
    baseline_ranked: List[str],
    canary_bucket: int = 0
) -> Tuple[List[Tuple[float, float, str, set]], Dict]:
    """
    GTB v0.3 Canary Mode 실제 적용
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (primary 기준 정렬됨)
        k: topK 값
        gap_p25: 동일 요청 내 topK 기준 gap_p25
        max_swaps: Swap budget (max_swaps = min(3, floor(K*0.1)))
        relevant_docs: relevant document ID 집합
        baseline_ranked: baseline 랭킹 (doc_id 리스트)
    
    Returns:
        (적용된 랭킹, 증빙 딕셔너리)
    """
    from gtb_v03_shadow import is_near_tie
    
    if len(ranked) < 2:
        return ranked, {
            "applied": False,
            "canary_bucket": canary_bucket,
            "swaps_applied_count": 0,
            "moved_up_count": 0,
            "moved_down_count": 0,
        }
    
    topk_ranked = ranked[:k].copy()  # 복사본 (원본 변경 방지)
    if len(topk_ranked) < 2:
        return ranked, {
            "applied": False,
            "canary_bucket": canary_bucket,
            "swaps_applied_count": 0,
            "moved_up_count": 0,
            "moved_down_count": 0,
        }
    
    # Baseline 랭킹에서 doc_id -> rank 매핑 생성
    baseline_rank_map = {}
    for idx, did in enumerate(baseline_ranked, 1):
        baseline_rank_map[did] = idx
    
    # Primary score와 gap 추출
    primary_scores = [p for p, _, _, _ in topk_ranked]
    gaps = []
    for i in range(len(primary_scores) - 1):
        gap = primary_scores[i] - primary_scores[i + 1]
        gaps.append(gap)
    
    # Near-tie 그룹 찾기 (gap <= gap_p25인 인접 쌍)
    near_tie_groups = []
    i = 0
    while i < len(topk_ranked) - 1:
        gap = gaps[i]
        if is_near_tie(gap, gap_p25):
            # Near-tie 그룹 시작
            group = [topk_ranked[i], topk_ranked[i + 1]]
            j = i + 1
            while j < len(topk_ranked) - 1 and is_near_tie(gaps[j], gap_p25):
                group.append(topk_ranked[j + 1])
                j += 1
            if len(group) > 1:
                near_tie_groups.append((i, group))  # (시작 인덱스, 그룹)
            i = j + 1
        else:
            i += 1
    
    # Swap budget 내에서 실제 적용
    swaps_applied = []
    moved_up_count = 0
    moved_down_count = 0
    
    for start_idx, group in near_tie_groups:
        if len(group) < 2:
            continue
        
        if len(swaps_applied) >= max_swaps:
            break  # Budget 초과
        
        # Baseline 순서 (원래 순서)
        baseline_dids = [did for _, _, did, _ in group]
        
        # Secondary signal로 재정렬 (실제 적용)
        shadow_order = sorted(group, key=lambda x: (-x[1], x[2]))  # secondary desc, doc_id asc
        shadow_dids = [did for _, _, did, _ in shadow_order]
        
        # 실제 swap 적용 (그룹 내에서만)
        for shadow_idx, (_, _, did, _) in enumerate(shadow_order):
            baseline_idx_in_group = baseline_dids.index(did) if did in baseline_dids else -1
            
            if baseline_idx_in_group == -1:
                continue
            
            if baseline_idx_in_group != shadow_idx:
                # 위치가 변경됨 (실제 적용)
                actual_baseline_idx = start_idx + baseline_idx_in_group
                actual_shadow_idx = start_idx + shadow_idx
                
                # Relevant 문서인지 확인
                is_relevant = str(did) in relevant_docs
                
                if shadow_idx < baseline_idx_in_group:
                    # 위로 이동
                    if is_relevant:
                        moved_up_count += 1
                else:
                    # 아래로 이동
                    if is_relevant:
                        moved_down_count += 1
                
                swaps_applied.append((did, actual_baseline_idx, actual_shadow_idx))
        
        # 실제 랭킹에 반영 (그룹 내에서만)
        for idx, item in enumerate(shadow_order):
            topk_ranked[start_idx + idx] = item
    
    # 전체 랭킹 재구성 (topk_ranked + 나머지)
    applied_ranked = topk_ranked + ranked[k:]
    
    return applied_ranked, {
        "applied": len(swaps_applied) > 0,
        "canary_bucket": canary_bucket,
        "swaps_applied_count": len(swaps_applied),
        "moved_up_count": moved_up_count,
        "moved_down_count": moved_down_count,
    }


if __name__ == "__main__":
    # Unit test용
    # Test 1: 결정론적 카나리 버킷
    request_id1 = "test-request-123"
    bucket1_1 = calculate_canary_bucket(request_id1)
    bucket1_2 = calculate_canary_bucket(request_id1)
    assert bucket1_1 == bucket1_2, f"Canary bucket not deterministic: {bucket1_1} != {bucket1_2}"
    assert 0 <= bucket1_1 < 100, f"Canary bucket out of range: {bucket1_1}"
    print("PASS: canary bucket deterministic")
    
    # Test 2: Fail-Closed (Meta-Guard gate_allow=false)
    assert should_apply_gtb_canary("test", 50, False) == False, "Should be disabled when gate_allow=False"
    print("PASS: Fail-Closed when gate_allow=False")
    
    # Test 3: 카나리 라우팅
    assert should_apply_gtb_canary("test", 0, True) == False, "Should be disabled when canary_percent=0"
    assert should_apply_gtb_canary("test", 100, True) == True, "Should be enabled when canary_percent=100"
    print("PASS: canary routing")
    
    print("OK: GTB v0.3 Canary Mode tests passed")

