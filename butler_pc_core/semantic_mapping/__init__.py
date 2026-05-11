"""semantic_mapping — 6단계 의미 매핑 파이프라인 (단계 1: 계약 + 타입 + 슬롯)."""
from .contracts import (
    ValueType,
    SourceField,
    TargetSlot,
    MappingCandidate,
    MappingDecision,
)
from .value_type_detector import detect_value_type
from .slot_schema import TARGET_SLOTS, SLOT_BY_ID

__all__ = [
    "ValueType",
    "SourceField",
    "TargetSlot",
    "MappingCandidate",
    "MappingDecision",
    "detect_value_type",
    "TARGET_SLOTS",
    "SLOT_BY_ID",
]
