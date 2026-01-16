#!/usr/bin/env python3
"""
GTB v0.3 Shadow Mode (meta-only)
랭킹을 변경하지 않고, tie-break가 적용되었다면 어떻게 될지 시뮬레이션
"""

import math
from typing import List, Tuple, Dict, Set


def calculate_swap_budget(k: int) -> int:
    """Swap budget 계산: max_swaps = min(3, floor(K*0.1))"""
    return min(3, int(math.floor(k * 0.1)))


def calculate_gap_p25_for_query(ranked: List[Tuple[float, float, str, set]], k: int) -> float:
    """동일 요청 내 topK 기준 gap_p25 계산"""
    if len(ranked) < 2:
        return 0.0
    
    topk_ranked = ranked[:k]
    if len(topk_ranked) < 2:
        return 0.0
    
    # Primary score 추출
    primary_scores = [p for p, _, _, _ in topk_ranked]
    
    # Gap 계산
    gaps = []
    for i in range(len(primary_scores) - 1):
        gap = primary_scores[i] - primary_scores[i + 1]
        gaps.append(gap)
    
    if not gaps:
        return 0.0
    
    # Percentile 계산 (간단한 버전)
    sorted_gaps = sorted(gaps)
    n = len(sorted_gaps)
    if n == 0:
        return 0.0
    
    idx = int((n - 1) * 0.25)
    return sorted_gaps[idx]


def is_near_tie(gap: float, gap_p25: float) -> bool:
    """Near-tie 판정: gap <= gap_p25"""
    return gap <= gap_p25


def simulate_gtb_v03_shadow(
    ranked: List[Tuple[float, float, str, set]],
    k: int,
    gap_p25: float,
    relevant_docs: set,
    baseline_ranked: List[str]
) -> Dict:
    """
    GTB v0.3 Shadow Mode 시뮬레이션 (primary-sorted invariance)
    
    모든 계산을 primary-score-monotonic view에서 수행하여 입력 순서와 무관하게
    동일한 카운터를 생성합니다.
    
    Args:
        ranked: [(primary, secondary, did, dt), ...] 리스트 (입력 순서 무관)
        k: topK 값
        gap_p25: 동일 요청 내 topK 기준 gap_p25
        relevant_docs: relevant document ID 집합
        baseline_ranked: baseline 랭킹 (doc_id 리스트)
    
    Returns:
        meta-only 카운트 딕셔너리 (shadow_reason_code 포함)
    """
    if len(ranked) < 2:
        return {
            "would_move_up_count": 0,
            "would_move_down_count": 0,
            "proposed_swap_count": 0,
            "budget_hit_count": 0,
            "shadow_reason_code": "",
        }
    
    # Primary-sorted view 생성 (stable sort by -primary_score, +original_index)
    primary_sorted_items = []
    for orig_idx, item in enumerate(ranked[:k]):
        primary_score, secondary_score, did, dt = item
        
        # Fail-Closed: primary_score missing/non-finite 체크
        if not isinstance(primary_score, (int, float)):
            return {
                "would_move_up_count": 0,
                "would_move_down_count": 0,
                "proposed_swap_count": 0,
                "budget_hit_count": 0,
                "shadow_reason_code": "GTB_SHADOW_PRIMARY_MISSING",
            }
        
        if not math.isfinite(primary_score):
            return {
                "would_move_up_count": 0,
                "would_move_down_count": 0,
                "proposed_swap_count": 0,
                "budget_hit_count": 0,
                "shadow_reason_code": "GTB_SHADOW_PRIMARY_MISSING",
            }
        
        primary_sorted_items.append((orig_idx, primary_score, secondary_score, did, dt))
    
    # Stable sort: -primary_score (desc), +orig_idx (asc) for ties
    try:
        primary_sorted_items.sort(key=lambda x: (-x[1], x[0]))
    except Exception as e:
        return {
            "would_move_up_count": 0,
            "would_move_down_count": 0,
            "proposed_swap_count": 0,
            "budget_hit_count": 0,
            "shadow_reason_code": "GTB_SHADOW_SORT_ERROR",
        }
    
    # primary_sorted view로 변환: (primary, secondary, did, dt)
    primary_sorted = [(p, s, d, dt) for _, p, s, d, dt in primary_sorted_items]
    
    if len(primary_sorted) < 2:
        return {
            "would_move_up_count": 0,
            "would_move_down_count": 0,
            "proposed_swap_count": 0,
            "budget_hit_count": 0,
            "shadow_reason_code": "",
        }
    
    # Swap budget 계산
    max_swaps = calculate_swap_budget(k)
    
    # Baseline 랭킹에서 doc_id -> rank 매핑 생성
    baseline_rank_map = {}
    for idx, did in enumerate(baseline_ranked, 1):
        baseline_rank_map[did] = idx
    
    # Primary score와 gap 추출 (primary_sorted view에서)
    primary_scores = [p for p, _, _, _ in primary_sorted]
    gaps = []
    for i in range(len(primary_scores) - 1):
        gap = primary_scores[i] - primary_scores[i + 1]
        gaps.append(gap)
    
    # Near-tie 그룹 찾기 (gap <= gap_p25인 인접 쌍, primary_sorted view에서)
    near_tie_groups = []
    i = 0
    while i < len(primary_sorted) - 1:
        gap = gaps[i]
        if is_near_tie(gap, gap_p25):
            # Near-tie 그룹 시작
            group = [primary_sorted[i], primary_sorted[i + 1]]
            j = i + 1
            while j < len(primary_sorted) - 1 and is_near_tie(gaps[j], gap_p25):
                group.append(primary_sorted[j + 1])
                j += 1
            if len(group) > 1:
                near_tie_groups.append(group)
            i = j + 1
        else:
            i += 1
    
    # 각 near-tie 그룹 내에서 secondary signal로 재정렬 시뮬레이션
    proposed_swaps = []
    would_move_up_count = 0
    would_move_down_count = 0
    
    for group in near_tie_groups:
        if len(group) < 2:
            continue
        
        # Baseline 순서 (primary_sorted view에서의 순서)
        baseline_dids = [did for _, _, did, _ in group]
        
        # Secondary signal로 재정렬 (Shadow only, 실제 적용 안 함)
        shadow_order = sorted(group, key=lambda x: (-x[1], x[2]))  # secondary desc, doc_id asc
        
        # 각 문서의 위치 변화 확인 (Shadow only, 실제 적용 안 함)
        for shadow_idx, (_, _, did, _) in enumerate(shadow_order):
            baseline_idx = baseline_dids.index(did) if did in baseline_dids else -1
            
            if baseline_idx == -1:
                continue  # Baseline에 없으면 스킵
            
            # Relevant 문서인지 확인 (doc_id는 문자열)
            is_relevant = str(did) in relevant_docs
            
            if baseline_idx != shadow_idx:
                # 위치가 변경됨 (Shadow only 카운트)
                if shadow_idx < baseline_idx:
                    # 위로 이동
                    if is_relevant:
                        would_move_up_count += 1
                    proposed_swaps.append((did, baseline_idx, shadow_idx))
                else:
                    # 아래로 이동 (그림자 카운트만)
                    if is_relevant:
                        would_move_down_count += 1
                    proposed_swaps.append((did, baseline_idx, shadow_idx))
    
    # Swap budget 확인
    proposed_swap_count = len(proposed_swaps)
    budget_hit_count = 1 if proposed_swap_count > max_swaps else 0
    
    return {
        "would_move_up_count": would_move_up_count,
        "would_move_down_count": would_move_down_count,
        "proposed_swap_count": proposed_swap_count,
        "budget_hit_count": budget_hit_count,
        "shadow_reason_code": "",
    }


if __name__ == "__main__":
    # Unit test용
    # Test 1: 결정론적 검증
    ranked_test = [
        (5.0, 0.5, "doc1", set()),
        (5.0, 0.3, "doc2", set()),  # near-tie (gap=0)
        (4.0, 0.0, "doc3", set()),
    ]
    gap_p25_test = 0.0  # gap <= 0이면 near-tie
    relevant_docs_test = {"doc1", "doc2"}
    baseline_ranked_test = ["doc1", "doc2", "doc3"]
    
    result1 = simulate_gtb_v03_shadow(ranked_test, 3, gap_p25_test, relevant_docs_test, baseline_ranked_test)
    result2 = simulate_gtb_v03_shadow(ranked_test, 3, gap_p25_test, relevant_docs_test, baseline_ranked_test)
    
    assert result1 == result2, f"Not deterministic: {result1} != {result2}"
    print("PASS: GTB v0.3 Shadow Mode deterministic")
    
    # Test 2: Swap budget
    assert calculate_swap_budget(5) == min(3, int(math.floor(5 * 0.1))) == 0
    assert calculate_swap_budget(20) == min(3, int(math.floor(20 * 0.1))) == 2
    assert calculate_swap_budget(50) == min(3, int(math.floor(50 * 0.1))) == 3
    print("PASS: Swap budget calculation")
    
    print("OK: GTB v0.3 Shadow Mode tests passed")

