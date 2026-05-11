"""test_semantic_mapping.py — D-4 의미 매핑 강화 (+5 테스트)."""
from __future__ import annotations

import pytest


# ── 공통 템플릿 ──────────────────────────────────────────────────────────────

_TEMPLATE_MD = (
    "# 사업 개요\n\n개요 설명\n\n"
    "## 사업 영역\n\n영역 설명\n\n"
    "## 사업 기간\n\n기간 명세\n\n"
    "## 예산 영역\n\n예산 명세\n\n"
    "## 일정\n\n일정 계획\n\n"
    "## 연락처\n\n연락처 정보"
).encode("utf-8")


def _transform(external_text: str):
    from butler_pc_core.document_transform.transform_pipeline import transform_document
    return transform_document(
        external_text.encode("utf-8"), "txt",
        _TEMPLATE_MD, "md",
    )


def _section_content(result, heading: str) -> str:
    for s in result.mapped_sections:
        if s.heading == heading:
            return s.content
    return ""


def _section_mapped(result, heading: str) -> bool:
    for s in result.mapped_sections:
        if s.heading == heading:
            return s.mapped
    return False


# ── 1. "기간" 키워드 → "사업 기간" 섹션 ────────────────────────────────────

def test_keyword_period_maps_to_business_period():
    """'기간: 6개월' → '사업 기간' 섹션에 정확히 매핑."""
    external = (
        "1. 협업 영역: AI 컨설팅\n"
        "2. 기간: 6개월\n"
        "3. 금액: 5천만원\n"
        "4. 시작일: 2026년 6월 1일\n"
        "연락처: contact@partner.com"
    )
    result = _transform(external)
    content = _section_content(result, "사업 기간")
    assert content != "", "사업 기간 섹션이 비어 있음 — '기간' 키워드가 매핑되지 않음"
    assert "기간" in content or "개월" in content, f"사업 기간 섹션 내용이 예상과 다름: {content!r}"


# ── 2. "금액" 키워드 → "예산 영역" 섹션 ────────────────────────────────────

def test_keyword_amount_maps_to_budget():
    """'금액: 5천만원' → '예산 영역' 섹션에 정확히 매핑."""
    external = (
        "1. 협업 영역: AI 컨설팅\n"
        "2. 기간: 6개월\n"
        "3. 금액: 5천만원\n"
        "4. 시작일: 2026년 6월 1일\n"
        "연락처: contact@partner.com"
    )
    result = _transform(external)
    content = _section_content(result, "예산 영역")
    assert content != "", "예산 영역 섹션이 비어 있음 — '금액' 키워드가 매핑되지 않음"
    assert "금액" in content or "만원" in content, f"예산 영역 섹션 내용이 예상과 다름: {content!r}"


# ── 3. "시작일" 키워드 → "일정" 섹션 ────────────────────────────────────────

def test_keyword_schedule_maps_to_schedule():
    """'시작일: 2026년 6월 1일' → '일정' 섹션에 정확히 매핑."""
    external = (
        "1. 협업 영역: AI 컨설팅\n"
        "2. 기간: 6개월\n"
        "3. 금액: 5천만원\n"
        "4. 시작일: 2026년 6월 1일\n"
        "연락처: contact@partner.com"
    )
    result = _transform(external)
    content = _section_content(result, "일정")
    assert content != "", "일정 섹션이 비어 있음 — '시작일' 키워드가 매핑되지 않음"
    assert "시작일" in content or "2026" in content, f"일정 섹션 내용이 예상과 다름: {content!r}"


# ── 4. "연락처" 키워드 → "연락처" 섹션 ──────────────────────────────────────

def test_keyword_contact_maps_to_contact():
    """'연락처: contact@partner.com' → '연락처' 섹션에 정확히 매핑."""
    external = (
        "1. 협업 영역: AI 컨설팅\n"
        "2. 기간: 6개월\n"
        "3. 금액: 5천만원\n"
        "4. 시작일: 2026년 6월 1일\n"
        "연락처: contact@partner.com"
    )
    result = _transform(external)
    content = _section_content(result, "연락처")
    assert content != "", "연락처 섹션이 비어 있음 — '연락처' 키워드가 매핑되지 않음"
    assert "연락처" in content or "contact" in content.lower(), f"연락처 섹션 내용이 예상과 다름: {content!r}"


# ── 5. 불확실 시 강제 매핑 X ──────────────────────────────────────────────────

def test_no_forced_mapping_when_uncertain():
    """
    외부 문서에 '사업 개요' 관련 키워드가 없으면 해당 섹션은 빈 채로 처리.
    잘못된 항목이 강제로 들어가면 안 됨.
    """
    external = (
        "기간: 12개월\n"
        "금액: 1억원\n"
        "연락처: admin@company.com"
    )
    result = _transform(external)

    # "사업 개요"에는 개요/요약/summary 관련 내용이 없으므로 비어야 함
    assert not _section_mapped(result, "사업 개요"), (
        "'사업 개요' 섹션에 관련 없는 항목이 강제 매핑됨 — "
        f"content={_section_content(result, '사업 개요')!r}"
    )

    # 매핑된 섹션은 올바른 섹션이어야 함 (기간, 예산, 연락처)
    assert _section_mapped(result, "사업 기간"), "'사업 기간' 섹션이 매핑되지 않음"
    assert _section_mapped(result, "예산 영역"), "'예산 영역' 섹션이 매핑되지 않음"
    assert _section_mapped(result, "연락처"), "'연락처' 섹션이 매핑되지 않음"
