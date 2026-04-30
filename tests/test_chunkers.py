"""test_chunkers.py — 파일 유형별 청커 21케이스 (유형당 3개: happy/boundary/adv)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from butler_pc_core.retrieval.chunkers import (
    Chunk,
    DocxChunker,
    EmailChunker,
    MeetingMinutesChunker,
    PdfReportChunker,
    PptChunker,
    ReceiptChunker,
    XlsxChunker,
    get_chunker,
)

# ─────────────────────────────────────────────
# MeetingMinutesChunker (3)
# ─────────────────────────────────────────────

def test_happy_meeting_agenda_splits_into_sections():
    content = (
        "## 회의 개요\n회의 참석자: 홍길동, 이순신\n\n"
        "## 1. 프로젝트 현황 보고\n현재 진행률 80%.\n\n"
        "## 2. 이슈 논의\n이슈 3건 확인.\n"
    )
    chunks = MeetingMinutesChunker().chunk(content, "meeting.txt")
    assert len(chunks) >= 3
    titles = [c.section_title for c in chunks]
    assert any("프로젝트 현황" in (t or "") for t in titles)


def test_boundary_meeting_long_section_subdivided():
    long_body = "A" * 3000
    content = f"## 긴 섹션\n{long_body}"
    chunks = MeetingMinutesChunker().chunk(content, "long.txt")
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c.text) <= MeetingMinutesChunker.MAX_CHUNK_CHARS + 10


def test_adv_meeting_no_headings_returns_chunks():
    content = "참석자 목록:\n홍길동\n이순신\n\n결론: 다음 주 재논의."
    chunks = MeetingMinutesChunker().chunk(content, "plain.txt")
    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)


# ─────────────────────────────────────────────
# PdfReportChunker (3)
# ─────────────────────────────────────────────

def test_happy_pdf_page_break_creates_separate_chunks():
    content = "서론\n\f2장 본론\n내용.\n\f3장 결론\n요약."
    chunks = PdfReportChunker().chunk(content, "report.pdf")
    pages = [c.page_or_sheet for c in chunks]
    assert 1 in pages and 2 in pages


def test_boundary_pdf_section_headers_split_within_page():
    content = (
        "1. 서론\n이 보고서는 X를 분석한다.\n\n"
        "2. 본론\n세부 분석 내용이 들어간다.\n\n"
        "3. 결론\n분석 결과 Y임을 확인하였다.\n"
    )
    chunks = PdfReportChunker().chunk(content, "doc.pdf")
    assert len(chunks) >= 2


def test_adv_pdf_empty_page_skipped():
    content = "첫 페이지\n\f\n\f세 번째 페이지"
    chunks = PdfReportChunker().chunk(content, "sparse.pdf")
    assert len(chunks) >= 2
    assert all(c.text.strip() for c in chunks)


# ─────────────────────────────────────────────
# DocxChunker (3)
# ─────────────────────────────────────────────

def test_happy_docx_headings_produce_sections():
    content = (
        "# 제목\n\n"
        "## 1장 서론\n서론 내용이 들어간다.\n\n"
        "## 2장 본론\n본론 내용이 들어간다.\n"
    )
    chunks = DocxChunker().chunk(content, "doc.docx")
    assert len(chunks) >= 2
    titles = [c.section_title for c in chunks if c.section_title]
    assert any("서론" in t for t in titles)


def test_boundary_docx_long_paragraph_split():
    long_para = "B" * 2500
    content = f"## 섹션\n\n{long_para}"
    chunks = DocxChunker().chunk(content, "big.docx")
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= DocxChunker.MAX_CHUNK_CHARS + 10


def test_adv_docx_multiple_blank_lines_normalized():
    content = "첫 문단.\n\n\n\n\n두 번째 문단."
    chunks = DocxChunker().chunk(content, "blanks.docx")
    assert len(chunks) >= 1
    joined = " ".join(c.text for c in chunks)
    assert "첫 문단" in joined and "두 번째 문단" in joined


# ─────────────────────────────────────────────
# XlsxChunker (3)
# ─────────────────────────────────────────────

def test_happy_xlsx_sheet_marker_creates_chunks():
    content = (
        "=== Sheet: 매출현황 ===\n"
        "날짜\t품목\t금액\n"
        + "\n".join(f"2026-01-{i+1:02d}\t상품{i}\t{i*1000}" for i in range(5))
    )
    chunks = XlsxChunker().chunk(content, "sales.xlsx")
    assert len(chunks) >= 1
    assert chunks[0].section_title == "매출현황"
    assert chunks[0].page_or_sheet == 1


def test_boundary_xlsx_many_rows_batched():
    rows = "\n".join(f"품목{i}\t{i}\t{i*500}" for i in range(80))
    content = f"=== Sheet: 재고 ===\n헤더A\t헤더B\t헤더C\n{rows}"
    chunks = XlsxChunker().chunk(content, "inventory.xlsx")
    assert len(chunks) >= 3
    for c in chunks:
        assert "헤더A" in c.text


def test_adv_xlsx_no_sheet_marker_treated_as_single_sheet():
    content = "품목\t수량\t단가\n사과\t10\t500\n배\t5\t800"
    chunks = XlsxChunker().chunk(content, "simple.csv")
    assert len(chunks) >= 1
    assert "품목" in chunks[0].text


# ─────────────────────────────────────────────
# EmailChunker (3)
# ─────────────────────────────────────────────

def test_happy_email_header_and_body_separate_chunks():
    content = (
        "From: alice@example.com\n"
        "To: bob@example.com\n"
        "Subject: 프로젝트 업데이트\n"
        "Date: 2026-04-01\n\n"
        "안녕하세요,\n오늘 회의 결과를 공유합니다.\n감사합니다."
    )
    chunks = EmailChunker().chunk(content, "email.eml")
    section_types = [c.section_title for c in chunks]
    assert "header" in section_types
    assert "body" in section_types


def test_boundary_email_quoted_lines_become_quoted_chunk():
    content = (
        "Subject: RE: 질문\n\n"
        "네, 확인했습니다.\n\n"
        "> 이전 메시지 내용입니다.\n"
        "> 추가 질문이 있습니다.\n"
    )
    chunks = EmailChunker().chunk(content, "reply.eml")
    quoted_chunks = [c for c in chunks if c.section_title == "quoted"]
    assert len(quoted_chunks) >= 1
    assert "> " in quoted_chunks[0].text


def test_adv_email_thread_separator_splits_messages():
    content = (
        "Subject: 첫 메시지\n\nOriginal content.\n"
        "----- Original Message -----\n"
        "Subject: 두 번째\n\nReplied content."
    )
    chunks = EmailChunker().chunk(content, "thread.eml")
    parts = {c.metadata.get("email_part") for c in chunks}
    assert len(parts) >= 2


# ─────────────────────────────────────────────
# PptChunker (3)
# ─────────────────────────────────────────────

def test_happy_ppt_slides_become_separate_chunks():
    content = (
        "=== Slide 1 ===\n[Title] 프로젝트 소개\n[Body] 프로젝트 개요입니다.\n"
        "=== Slide 2 ===\n[Title] 주요 성과\n[Body] 목표 달성 100%.\n"
        "=== Slide 3 ===\n[Title] 결론\n[Body] 계속 진행 예정.\n"
    )
    chunks = PptChunker().chunk(content, "presentation.pptx")
    assert len(chunks) == 3
    assert chunks[0].page_or_sheet == 1
    assert chunks[1].page_or_sheet == 2


def test_boundary_ppt_long_slide_subdivided():
    long_body = "C" * 2500
    content = f"=== Slide 1 ===\n[Title] 긴 슬라이드\n[Body] {long_body}"
    chunks = PptChunker().chunk(content, "long_slide.pptx")
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= PptChunker.MAX_CHUNK_CHARS + 10


def test_adv_ppt_no_slide_markers_single_chunk():
    content = "[Title] 단독 슬라이드\n[Body] 내용이 여기에."
    chunks = PptChunker().chunk(content, "single.pptx")
    assert len(chunks) >= 1
    assert "단독 슬라이드" in chunks[0].text


# ─────────────────────────────────────────────
# ReceiptChunker (3)
# ─────────────────────────────────────────────

def test_happy_receipt_single_receipt_one_chunk():
    content = (
        "가게명: 테스트마트\n"
        "날짜: 2026-04-01\n"
        "우유          1  1500\n"
        "빵            2  2000\n"
        "합계: 5500원"
    )
    chunks = ReceiptChunker().chunk(content, "receipt.txt")
    assert len(chunks) == 1
    assert "합계" in chunks[0].text


def test_boundary_receipt_separator_creates_multiple_chunks():
    receipt_block = (
        "가게명: A마트\n날짜: 2026-01-01\n"
        "물           1  1000\n합계: 1000원\n"
    )
    content = receipt_block + "===\n" + receipt_block.replace("A마트", "B마트")
    chunks = ReceiptChunker().chunk(content, "receipts.txt")
    assert len(chunks) >= 2


def test_adv_receipt_many_items_batched():
    header = "가게명: 테스트슈퍼마켓\n날짜: 2026-03-01\n담당자: 홍길동\n"
    items = "\n".join(f"상품{i:<8}  1  {10000+i}" for i in range(80))
    footer = "소계: 800000원\n부가세: 80000원\n합계: 880000원"
    content = header + items + "\n" + footer
    chunks = ReceiptChunker().chunk(content, "big_receipt.txt")
    assert len(chunks) >= 2
    assert all(c.text.strip() for c in chunks)


# ─────────────────────────────────────────────
# EmailChunker 결함 1 회귀 테스트
# ─────────────────────────────────────────────

def test_adv_email_header_preserves_full_lines():
    """결함 1 회귀: 헤더 본문(주소·제목·날짜)이 청크에 보존된다."""
    content = (
        "From: kim@acme.com\n"
        "To: lee@partner.com\n"
        "Subject: Q3 보고서 검토 부탁드립니다\n"
        "Date: 2026-04-15\n\n"
        "본문 시작..."
    )
    chunks = EmailChunker().chunk(content, "regression.eml")
    header_chunks = [c for c in chunks if c.section_title == "header"]
    assert len(header_chunks) > 0, "헤더 chunk 없음"
    header_text = header_chunks[0].text
    assert "kim@acme.com" in header_text, f"발신 주소 누락: {header_text!r}"
    assert "lee@partner.com" in header_text, f"수신 주소 누락: {header_text!r}"
    assert "Q3 보고서 검토 부탁드립니다" in header_text, f"제목 누락: {header_text!r}"
    assert "2026-04-15" in header_text, f"날짜 누락: {header_text!r}"
    assert header_text.strip() not in {"From\nTo\nSubject\nDate", ""}, \
        f"필드명만 추출된 결함 재발: {header_text!r}"


def test_adv_email_search_by_sender_finds_correct_chunk():
    """발신자 이름·주소가 청크에 포함되어 검색 가능하다."""
    content = (
        "From: 김부장 <kim@acme.com>\n"
        "Subject: 분기 보고서\n\n"
        "본문 내용입니다."
    )
    chunks = EmailChunker().chunk(content, "sender.eml")
    full_text = " ".join(c.text for c in chunks)
    assert "김부장" in full_text, "발신자 이름 검색 불가"
    assert "kim@acme.com" in full_text, "발신자 주소 검색 불가"


def test_happy_email_body_chunked_separately():
    """본문은 헤더와 별도 section_title='body' chunk로 분리된다."""
    content = (
        "From: a@b.com\n"
        "Subject: Test\n\n"
        "This is the body content.\n"
        "Multiple paragraphs.\n\n"
        "Another paragraph."
    )
    chunks = EmailChunker().chunk(content, "body_test.eml")
    section_titles = {c.section_title for c in chunks}
    assert "header" in section_titles
    assert "body" in section_titles


# ─────────────────────────────────────────────
# dispatcher (bonus — not counted in 21)
# ─────────────────────────────────────────────

def test_adv_dispatcher_routes_by_extension():
    assert isinstance(get_chunker(file_path="doc.pdf"), PdfReportChunker)
    assert isinstance(get_chunker(file_path="data.xlsx"), XlsxChunker)
    assert isinstance(get_chunker(file_type="receipt"), ReceiptChunker)
    assert isinstance(get_chunker(file_path="unknown.xyz"), MeetingMinutesChunker)
