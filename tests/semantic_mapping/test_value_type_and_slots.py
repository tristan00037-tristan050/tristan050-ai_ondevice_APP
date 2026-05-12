"""test_value_type_and_slots.py — D-4 semantic_mapping 단계 1 검증 (+10)."""
from __future__ import annotations

import pytest

from butler_pc_core.semantic_mapping.contracts import ValueType
from butler_pc_core.semantic_mapping.value_type_detector import detect_value_type
from butler_pc_core.semantic_mapping.slot_schema import TARGET_SLOTS, SLOT_BY_ID


# ── value_type_detector 영역 (7개) ────────────────────────────────────────────

def test_detect_email_from_value():
    """이메일 주소가 값에 있으면 EMAIL."""
    assert detect_value_type("연락처", "contact@partner.com") == ValueType.EMAIL


def test_detect_email_label_and_value():
    """'이메일' 레이블 + @ 값 → EMAIL."""
    assert detect_value_type("이메일", "admin@company.com") == ValueType.EMAIL


def test_detect_phone_korean_format():
    """한국 전화번호 패턴 → PHONE."""
    assert detect_value_type("전화", "010-1234-5678") == ValueType.PHONE


def test_detect_money_cheonman_won():
    """'5천만원' 한국어 금액 → MONEY."""
    assert detect_value_type("금액", "5천만원") == ValueType.MONEY


def test_detect_money_eok_won():
    """'1억원' 값 → MONEY."""
    assert detect_value_type("예산", "1억원") == ValueType.MONEY


def test_detect_date_range_months():
    """'6개월' → DATE_RANGE (DATE 아님)."""
    result = detect_value_type("기간", "6개월")
    assert result == ValueType.DATE_RANGE


def test_detect_date_range_label_hint():
    """'기한' 레이블 단독으로도 DATE_RANGE."""
    assert detect_value_type("기한", "12개월") == ValueType.DATE_RANGE


def test_detect_date_start():
    """'시작일: 2026년 6월 1일' → DATE."""
    assert detect_value_type("시작일", "2026년 6월 1일") == ValueType.DATE


def test_detect_date_iso_format():
    """ISO 날짜 형식 2026-06-01 → DATE."""
    assert detect_value_type("날짜", "2026-06-01") == ValueType.DATE


def test_detect_category_area_label():
    """'사업 영역' 레이블 → CATEGORY."""
    assert detect_value_type("사업 영역", "AI 컨설팅") == ValueType.CATEGORY


# ── slot_schema 영역 (4개) ────────────────────────────────────────────────────

def test_slot_schema_has_6_slots():
    """TARGET_SLOTS 정확히 6개."""
    assert len(TARGET_SLOTS) == 6


def test_slot_business_period_allows_date_range():
    """business_period 슬롯은 DATE_RANGE 허용."""
    slot = SLOT_BY_ID["business_period"]
    assert ValueType.DATE_RANGE in slot.allowed_types


def test_slot_budget_allows_money():
    """budget 슬롯은 MONEY 허용."""
    slot = SLOT_BY_ID["budget"]
    assert ValueType.MONEY in slot.allowed_types


def test_slot_contact_allows_email_and_phone():
    """contact 슬롯은 EMAIL + PHONE 모두 허용 (one-to-many collapse 방지 핵심)."""
    slot = SLOT_BY_ID["contact"]
    assert ValueType.EMAIL in slot.allowed_types
    assert ValueType.PHONE in slot.allowed_types
