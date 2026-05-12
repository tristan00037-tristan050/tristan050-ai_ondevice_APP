"""contracts.py — semantic_mapping 공통 데이터 계약."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ValueType(Enum):
    TEXT = "text"
    DATE = "date"
    DATE_RANGE = "date_range"
    MONEY = "money"
    PHONE = "phone"
    EMAIL = "email"
    PERSON = "person"
    ORG = "org"
    CATEGORY = "category"
    UNKNOWN = "unknown"


@dataclass
class SourceField:
    """외부 문서에서 추출된 단일 필드."""
    label: str
    value: str
    raw_text: str
    detected_type: ValueType = ValueType.UNKNOWN


@dataclass
class TargetSlot:
    """우리 양식의 단일 섹션 슬롯 정의."""
    slot_id: str
    heading: str
    level: int
    allowed_types: List[ValueType]
    aliases: List[str]
    required: bool = False


@dataclass
class MappingCandidate:
    """특정 (소스 필드, 타깃 슬롯) 쌍의 점수."""
    source_field: SourceField
    target_slot: TargetSlot
    semantic_score: float = 0.0   # 0.0 ~ 1.0
    type_score: float = 0.0       # 0.0 ~ 1.0
    combined_score: float = 0.0   # 최종 결합 점수


@dataclass
class MappingDecision:
    """슬롯 단위 최종 결정."""
    target_slot: TargetSlot
    source_field: Optional[SourceField]
    confidence: float             # 0.0 ~ 1.0
    needs_review: bool
    mapped: bool
