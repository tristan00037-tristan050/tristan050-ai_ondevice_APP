"""tests/request_parsing/test_exporters.py — Markdown / docx 출력 테스트."""
import pytest

from butler_pc_core.request_parsing.parser import (
    ActionItem,
    Deadline,
    Intent,
    MaterialItem,
    ParsedResult,
)
from butler_pc_core.request_parsing.exporters import result_to_markdown, result_to_docx_bytes


def _make_result(confidence: float = 0.88) -> ParsedResult:
    r = ParsedResult()
    r.actions = [
        ActionItem(text="계약서 검토 및 날인", priority="P1", rationale="긴급 요청"),
        ActionItem(text="손익계산서 첨부", priority="P2"),
    ]
    r.deadline = Deadline(raw_text="다음 주 화요일", parsed_date="2026-05-19", confidence=0.9)
    r.required_materials = [
        MaterialItem(name="손익계산서", is_optional=False, rationale="필수 첨부"),
        MaterialItem(name="기타 자료", is_optional=True),
    ]
    r.intent = Intent(
        summary="계약서 검토 요청",
        tone="formal",
        expected_response="검토 완료 후 날인 회신",
    )
    r.confidence = confidence
    r.masked_text = "원문 마스킹 텍스트"
    r.input_format = "email"
    return r


def test_markdown_contains_action():
    md = result_to_markdown(_make_result())
    assert "계약서 검토 및 날인" in md
    assert "P1" in md


def test_markdown_contains_deadline():
    md = result_to_markdown(_make_result())
    assert "다음 주 화요일" in md
    assert "2026-05-19" in md


def test_markdown_contains_materials():
    md = result_to_markdown(_make_result())
    assert "손익계산서" in md
    assert "(선택)" in md  # 기타 자료 optional


def test_markdown_confidence_shown():
    md = result_to_markdown(_make_result(confidence=0.88))
    assert "88%" in md


def test_docx_returns_bytes():
    pytest.importorskip("docx", reason="python-docx 미설치 — 건너뜀")
    data = result_to_docx_bytes(_make_result())
    assert isinstance(data, bytes)
    # OOXML signature: PK (zip)
    assert data[:2] == b"PK"


def test_docx_error_without_python_docx(monkeypatch):
    """python-docx가 없으면 ParseError를 올려야 한다."""
    import sys
    monkeypatch.setitem(sys.modules, "docx", None)
    from butler_pc_core.request_parsing.parser import ParseError
    with pytest.raises(ParseError):
        result_to_docx_bytes(_make_result())
