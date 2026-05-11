"""slot_schema.py — D-4 카드 2 타깃 슬롯 정의 (6개)."""
from __future__ import annotations

from .contracts import TargetSlot, ValueType

TARGET_SLOTS: list[TargetSlot] = [
    TargetSlot(
        slot_id="business_overview",
        heading="사업 개요",
        level=1,
        allowed_types=[ValueType.TEXT, ValueType.CATEGORY],
        aliases=["개요", "요약", "summary", "overview", "소개", "배경", "목적", "제안", "목표"],
        required=False,
    ),
    TargetSlot(
        slot_id="business_area",
        heading="사업 영역",
        level=2,
        allowed_types=[ValueType.TEXT, ValueType.CATEGORY],
        aliases=["영역", "분야", "scope", "범위", "역할", "업무", "서비스"],
        required=True,
    ),
    TargetSlot(
        slot_id="business_period",
        heading="사업 기간",
        level=2,
        allowed_types=[ValueType.DATE_RANGE, ValueType.TEXT],
        aliases=["기간", "기한", "duration", "period", "개월", "주간", "연간"],
        required=True,
    ),
    TargetSlot(
        slot_id="budget",
        heading="예산 영역",
        level=2,
        allowed_types=[ValueType.MONEY, ValueType.TEXT],
        aliases=["예산", "금액", "budget", "비용", "fee", "cost", "가격", "견적"],
        required=True,
    ),
    TargetSlot(
        slot_id="schedule",
        heading="일정",
        level=2,
        allowed_types=[ValueType.DATE, ValueType.DATE_RANGE, ValueType.TEXT],
        aliases=["일정", "시작일", "착수일", "schedule", "날짜", "date", "종료일", "완료일", "마감일"],
        required=False,
    ),
    TargetSlot(
        slot_id="contact",
        heading="연락처",
        level=2,
        allowed_types=[ValueType.EMAIL, ValueType.PHONE, ValueType.PERSON, ValueType.TEXT],
        aliases=["연락처", "이메일", "email", "전화", "phone", "tel", "contact", "담당자", "수신인"],
        required=False,
    ),
]

SLOT_BY_ID: dict[str, TargetSlot] = {s.slot_id: s for s in TARGET_SLOTS}
