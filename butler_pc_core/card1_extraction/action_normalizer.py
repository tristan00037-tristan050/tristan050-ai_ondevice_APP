"""action_normalizer.py — 단계 6.5.2 Patch 2 (알고리즘 팀 §6).

action verb normalization — '보내/보내기/전달' 류를 동일 그룹으로 통합.
평가 시 strict / normalized 2가지 매칭 모드 병행 집계 가능.

semantic_action_match (LLM 추가 검증)는 6.5.3 이후.
"""
from __future__ import annotations

from typing import Dict, List


# 동사 → normalized 그룹 (longest-prefix matching을 위한 dict 키 순서 중요)
ACTION_NORMALIZE: Dict[str, str] = {
    "보내기":    "send",
    "보내":      "send",
    "전달":      "send",
    "송부":      "send",
    "공유하기":  "share",
    "공유":      "share",
    "정리하기":  "organize",
    "정리":      "organize",
    "취합":      "organize",
    "검토":      "review",
    "확인":      "review",
    "수정":      "revise",
    "반영":      "revise",
    "보완":      "revise",
    "제출":      "submit",
    "회신":      "submit",
    "업로드":    "upload",
    "첨부":      "upload",
}

# 평가용 출력 그룹 라벨
NORMALIZED_LABELS: List[str] = sorted(set(ACTION_NORMALIZE.values()))


def normalize_action_verb(text: str) -> str:
    """텍스트에 포함된 첫 매칭 키워드 → normalized 그룹.

    매칭 우선순위: ACTION_NORMALIZE 선언 순서 (긴 키 우선이 되도록 사전 정렬됨).
    매칭 없으면 'other'.
    """
    if not text:
        return "other"
    for key, group in ACTION_NORMALIZE.items():
        if key in text:
            return group
    return "other"
