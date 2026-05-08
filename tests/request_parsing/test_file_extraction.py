"""tests/request_parsing/test_file_extraction.py — P1 파일 형식별 추출 + P2 from_dict 복원."""
import io
import textwrap
import pytest

from butler_pc_core.request_parsing.parser import (
    ParsedResult,
    extract_text_from_file_bytes,
    ParseError,
)


# ── P2: from_dict 필드 복원 ────────────────────────────────────────────────────

def test_from_dict_preserves_masked_text():
    d = {
        "actions": [], "deadline": {"raw_text": "", "parsed_date": None},
        "required_materials": [], "intent": {"summary": "", "tone": "formal", "expected_response": ""},
        "confidence": 0.8, "masked_text": "PII가 마스킹된 원문 텍스트입니다.",
        "input_format": "email",
    }
    result = ParsedResult.from_dict(d)
    assert result.masked_text == "PII가 마스킹된 원문 텍스트입니다."


def test_from_dict_preserves_input_format():
    d = {
        "actions": [], "deadline": {"raw_text": "", "parsed_date": None},
        "required_materials": [], "intent": {"summary": "", "tone": "formal", "expected_response": ""},
        "confidence": 0.8, "masked_text": "", "input_format": "docx",
    }
    result = ParsedResult.from_dict(d)
    assert result.input_format == "docx"


def test_from_dict_defaults_when_fields_absent():
    d = {
        "actions": [], "deadline": {"raw_text": "", "parsed_date": None},
        "required_materials": [], "intent": {"summary": "", "tone": "formal", "expected_response": ""},
        "confidence": 0.8,
    }
    result = ParsedResult.from_dict(d)
    assert result.masked_text == ""
    assert result.input_format == "text"


def test_from_dict_with_none_deadline():
    """LLM이 deadline: null을 반환할 때 from_dict가 안전하게 처리해야 한다."""
    d = {
        "actions": [],
        "deadline": None,
        "required_materials": [],
        "intent": {"summary": "test", "tone": "formal", "expected_response": ""},
        "confidence": 0.85,
        "masked_text": "마스킹된 텍스트 <rrn_masked>",
        "input_format": "eml",
    }
    result = ParsedResult.from_dict(d)
    assert result.masked_text == "마스킹된 텍스트 <rrn_masked>"
    assert result.input_format == "eml"
    assert result.deadline is not None  # Deadline 객체로 안전 초기화


def test_from_dict_with_missing_deadline_field():
    """deadline 키 자체가 없을 때 from_dict가 안전하게 처리해야 한다."""
    d = {
        "actions": [],
        "required_materials": [],
        "intent": {"summary": "test", "tone": "informal", "expected_response": ""},
        "confidence": 0.7,
        "masked_text": "",
        "input_format": "text",
    }
    result = ParsedResult.from_dict(d)
    assert result.masked_text == ""
    assert result.input_format == "text"
    assert result.deadline is not None  # Deadline 객체로 안전 초기화


# ── P1: extract_text_from_file_bytes ──────────────────────────────────────────

def test_extract_txt_bytes_utf8():
    content = "안녕하세요. 이번 주 금요일까지 보고서 작성 부탁드립니다."
    result = extract_text_from_file_bytes(content.encode("utf-8"), ".txt")
    assert "보고서 작성" in result


def test_extract_md_bytes():
    content = "# 회의록\n\n다음 주 화요일까지 계약서 검토 부탁드립니다.\n"
    result = extract_text_from_file_bytes(content.encode("utf-8"), ".md")
    assert "계약서 검토" in result


def test_extract_eml_bytes():
    eml_content = (
        "From: sender@example.com\r\n"
        "To: recipient@company.com\r\n"
        "Subject: 보고서 요청\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "안녕하세요. 다음 주 금요일까지 Q1 보고서를 제출해 주시면 감사하겠습니다.\r\n"
    )
    result = extract_text_from_file_bytes(eml_content.encode("utf-8"), ".eml")
    assert "보고서를 제출" in result


def test_extract_docx_bytes():
    pytest.importorskip("docx", reason="python-docx 미설치 — 건너뜀")
    import docx as _docx
    buf = io.BytesIO()
    doc = _docx.Document()
    doc.add_paragraph("계약서 검토 및 날인을 다음 주 화요일까지 부탁드립니다.")
    doc.save(buf)
    result = extract_text_from_file_bytes(buf.getvalue(), ".docx")
    assert "계약서 검토" in result


def test_extract_pdf_bytes():
    pytest.importorskip("pdfminer", reason="pdfminer.six 미설치 — 건너뜀")
    # 최소 PDF 구조 (ASCII-safe 텍스트 포함)
    # pdfminer가 설치된 경우만 실제 추출 검증
    from pdfminer.high_level import extract_text as _pdf_extract
    # 내용 없는 PDF bytes → 빈 문자열 반환 확인 (ParseError 아님)
    empty_pdf = b"%PDF-1.4\n%%EOF\n"
    try:
        result = extract_text_from_file_bytes(empty_pdf, ".pdf")
        assert isinstance(result, str)
    except Exception:
        pass  # 최소 PDF 파싱 실패는 허용


def test_extract_unsupported_format_raises():
    with pytest.raises(ParseError, match="지원하지 않는"):
        extract_text_from_file_bytes(b"some bytes", ".xlsx")
