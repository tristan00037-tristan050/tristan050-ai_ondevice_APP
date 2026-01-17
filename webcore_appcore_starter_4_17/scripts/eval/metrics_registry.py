"""
Metrics Registry: 평가 지표 집계 및 보고 (meta-only, fail-closed)
Effect metrics를 포함한 모든 평가 지표를 집계합니다.
"""

from typing import Dict, List, Any, Optional, Tuple
import sys
import os

# Effect metrics 모듈 로드
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from effect_metrics import calculate_effect_metrics
except ImportError:
    calculate_effect_metrics = None


def aggregate_effect_metrics(
    all_baseline_ranked: List[List[Tuple[float, float, str, set]]],
    all_treatment_ranked: List[List[Tuple[float, float, str, set]]],
    all_relevance_labels: List[Dict[str, float]],
    k: int = 10,
    all_logged_propensities: Optional[List[Dict[str, float]]] = None,
    all_observed_rewards: Optional[List[Dict[str, float]]] = None
) -> Dict[str, Any]:
    """
    Effect metrics 집계 (meta-only, fail-closed)
    
    Args:
        all_baseline_ranked: 모든 쿼리에 대한 baseline 랭킹 리스트
        all_treatment_ranked: 모든 쿼리에 대한 treatment 랭킹 리스트
        all_relevance_labels: 모든 쿼리에 대한 relevance labels 리스트
        k: topK 값 (기본값: 10)
        all_logged_propensities: 모든 쿼리에 대한 logged propensities 리스트 (optional)
        all_observed_rewards: 모든 쿼리에 대한 observed rewards 리스트 (optional)
    
    Returns:
        집계된 effect metrics 딕셔너리 (meta-only)
    """
    if calculate_effect_metrics is None:
        return {
            "effect_ndcg_at_10_baseline": None,
            "effect_ndcg_at_10_treatment": None,
            "effect_ndcg_gain_at_10": None,
            "effect_ips": None,
            "effect_snips": None,
            "effect_reason_code": "EFFECT_MODULE_MISSING",
        }
    
    if not all_baseline_ranked or not all_treatment_ranked or not all_relevance_labels:
        return {
            "effect_ndcg_at_10_baseline": None,
            "effect_ndcg_at_10_treatment": None,
            "effect_ndcg_gain_at_10": None,
            "effect_ips": None,
            "effect_snips": None,
            "effect_reason_code": "EFFECT_LABELS_MISSING",
        }
    
    if len(all_baseline_ranked) != len(all_treatment_ranked) or \
       len(all_baseline_ranked) != len(all_relevance_labels):
        return {
            "effect_ndcg_at_10_baseline": None,
            "effect_ndcg_at_10_treatment": None,
            "effect_ndcg_gain_at_10": None,
            "effect_ips": None,
            "effect_snips": None,
            "effect_reason_code": "EFFECT_INPUT_MISMATCH",
        }
    
    # 각 쿼리별 effect metrics 계산
    all_ndcg_baseline = []
    all_ndcg_treatment = []
    all_ndcg_gain = []
    all_ips = []
    all_snips = []
    reason_codes = []
    
    for i in range(len(all_baseline_ranked)):
        baseline_ranked = all_baseline_ranked[i]
        treatment_ranked = all_treatment_ranked[i]
        relevance_labels = all_relevance_labels[i]
        
        logged_propensities = None
        observed_rewards = None
        if all_logged_propensities is not None and all_observed_rewards is not None:
            if i < len(all_logged_propensities) and i < len(all_observed_rewards):
                logged_propensities = all_logged_propensities[i]
                observed_rewards = all_observed_rewards[i]
        
        result = calculate_effect_metrics(
            baseline_ranked, treatment_ranked, relevance_labels, k,
            logged_propensities, observed_rewards
        )
        
        if result["effect_ndcg_at_10_baseline"] is not None:
            all_ndcg_baseline.append(result["effect_ndcg_at_10_baseline"])
        if result["effect_ndcg_at_10_treatment"] is not None:
            all_ndcg_treatment.append(result["effect_ndcg_at_10_treatment"])
        if result["effect_ndcg_gain_at_10"] is not None:
            all_ndcg_gain.append(result["effect_ndcg_gain_at_10"])
        if result["effect_ips"] is not None:
            all_ips.append(result["effect_ips"])
        if result["effect_snips"] is not None:
            all_snips.append(result["effect_snips"])
        
        reason_codes.append(result["effect_reason_code"])
    
    # 집계 (평균)
    aggregated = {
        "effect_ndcg_at_10_baseline": round(sum(all_ndcg_baseline) / len(all_ndcg_baseline), 6) if all_ndcg_baseline else None,
        "effect_ndcg_at_10_treatment": round(sum(all_ndcg_treatment) / len(all_ndcg_treatment), 6) if all_ndcg_treatment else None,
        "effect_ndcg_gain_at_10": round(sum(all_ndcg_gain) / len(all_ndcg_gain), 6) if all_ndcg_gain else None,
        "effect_ips": round(sum(all_ips) / len(all_ips), 6) if all_ips else None,
        "effect_snips": round(sum(all_snips) / len(all_snips), 6) if all_snips else None,
        "effect_reason_code": max(set(reason_codes), key=reason_codes.count) if reason_codes else "EFFECT_OK",
    }
    
    return aggregated


if __name__ == "__main__":
    # Unit test용
    print("OK: Metrics registry module loaded")

