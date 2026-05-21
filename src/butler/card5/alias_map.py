"""Card 5 v3 alias map.

순서:
1. 47 allowlist exact match 우선 통과
2. 12 alias 정규화
3. 둘 다 아니면 hallucination
"""
from __future__ import annotations

from .allowlist import allowed_titles, title_to_code_map

ALIAS_MAP_12: dict[str, str] = {
    "서비스매출": "용역매출",
    "임대수익": "임대료수익",
    "대출이자비용": "이자비용",
    "사무실 월세": "지급임차료",
    "사무실월세": "지급임차료",
    "재고자산상각비": "상품매출원가",
    "원료비": "제품매출원가",
    "제품비": "상품매출원가",
    "하도급원가": "용역원가",
    "개발비": "용역원가",
    "보험수리적손실": "잡손실",
    "용역수익": "용역매출",
    "제품원가": "제품매출원가",
}


def apply_alias(predicted_title: str, predicted_code: str) -> tuple[str, str, str]:
    title = (predicted_title or "").strip()
    code_map = title_to_code_map()
    titles = allowed_titles()

    if title in titles:
        expected_code = code_map[title]
        return title, expected_code, "exact"

    if title in ALIAS_MAP_12:
        corrected_title = ALIAS_MAP_12[title]
        corrected_code = code_map[corrected_title]
        return corrected_title, corrected_code, "alias_mapped"

    return title, predicted_code, "hallucination"
