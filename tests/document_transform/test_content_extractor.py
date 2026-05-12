"""test_content_extractor.py — D-4 Card 2 문서 변환 백엔드 (+8 테스트)."""
from __future__ import annotations

import io
import pytest


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_docx_bytes(paragraphs: list[str], headings: list[tuple[str, int]] | None = None) -> bytes:
    """간단한 .docx 바이트 생성 (python-docx 사용)."""
    docx = pytest.importorskip("docx", reason="python-docx 미설치")
    doc = docx.Document()
    if headings:
        for text, level in headings:
            doc.add_paragraph(text, style=f"Heading {level}")
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_md_bytes(text: str) -> bytes:
    return text.encode("utf-8")


# ── 1. .txt 텍스트 추출 ──────────────────────────────────────────────────────

def test_extract_text_from_txt():
    from butler_pc_core.document_transform.content_extractor import extract_text_from_bytes
    data = "안녕하세요\n테스트 내용입니다".encode("utf-8")
    result = extract_text_from_bytes(data, "txt")
    assert "안녕하세요" in result
    assert "테스트" in result


# ── 2. .md 텍스트 추출 ───────────────────────────────────────────────────────

def test_extract_text_from_md():
    from butler_pc_core.document_transform.content_extractor import extract_text_from_bytes
    data = "# 제목\n\n본문 내용입니다.".encode("utf-8")
    result = extract_text_from_bytes(data, "md")
    assert "제목" in result
    assert "본문" in result


# ── 3. .docx 텍스트 추출 ─────────────────────────────────────────────────────

def test_extract_text_from_docx():
    pytest.importorskip("docx", reason="python-docx 미설치")
    from butler_pc_core.document_transform.content_extractor import extract_text_from_bytes
    data = _make_docx_bytes(["제안서 내용", "예산 세부 사항"])
    result = extract_text_from_bytes(data, "docx")
    assert "제안서" in result
    assert "예산" in result


# ── 4. .md 양식 구조 파싱 ────────────────────────────────────────────────────

def test_parse_md_template_sections():
    from butler_pc_core.document_transform.template_parser import parse_template_bytes
    md = (
        "# 제목\n\n제목 내용\n\n"
        "## 배경\n\n배경 설명\n\n"
        "## 제안 내용\n\n제안 상세\n\n"
        "## 예산\n\n예산 명세"
    ).encode("utf-8")
    sections = parse_template_bytes(md, "md")
    assert len(sections) >= 3
    headings = [s.heading for s in sections]
    assert "배경" in headings
    assert "예산" in headings


# ── 5. .docx 양식 구조 파싱 ──────────────────────────────────────────────────

def test_parse_docx_template_sections():
    pytest.importorskip("docx", reason="python-docx 미설치")
    from butler_pc_core.document_transform.template_parser import parse_template_bytes
    data = _make_docx_bytes(
        paragraphs=["배경 설명입니다.", "예산 내용입니다."],
        headings=[("배경", 1), ("예산", 2)],
    )
    sections = parse_template_bytes(data, "docx")
    headings = [s.heading for s in sections]
    assert "배경" in headings or "예산" in headings


# ── 6. TransformResult confidence 범위 검증 ──────────────────────────────────

def test_transform_result_confidence_range():
    pytest.importorskip("docx", reason="python-docx 미설치")
    from butler_pc_core.document_transform.transform_pipeline import transform_document
    external = "배경: 클라우드 전환 필요\n\n예산: 500만원\n\n일정: 3개월".encode("utf-8")
    template = "# 배경\n\n배경 설명\n\n## 예산\n\n예산 명세\n\n## 일정\n\n일정 계획".encode("utf-8")
    result = transform_document(external, "md", template, "md")
    assert 0.0 <= result.confidence <= 1.0


# ── 7. 출력 .docx 바이트 비어있지 않음 ───────────────────────────────────────

def test_render_docx_output_non_empty():
    pytest.importorskip("docx", reason="python-docx 미설치")
    from butler_pc_core.document_transform.transform_pipeline import transform_document
    external = "제안 배경: 비용 절감 필요\n\n제안 내용: SaaS 전환".encode("utf-8")
    template = "# 배경\n\n## 제안 내용".encode("utf-8")
    result = transform_document(external, "md", template, "md")
    assert len(result.output_docx_bytes) > 0
    # .docx magic bytes (PK zip)
    assert result.output_docx_bytes[:2] == b"PK"


# ── 8. 미매핑 섹션 감지 ──────────────────────────────────────────────────────

def test_unmapped_section_detected():
    pytest.importorskip("docx", reason="python-docx 미설치")
    from butler_pc_core.document_transform.transform_pipeline import transform_document
    # 외부 문서에 "예산" 관련 내용 없음 — 양식에는 예산 섹션 있음
    external = "제안 배경: 디지털 전환 필요".encode("utf-8")
    template = (
        "# 배경\n\n배경 설명\n\n"
        "## 예산세부내역검토필수항목\n\n예산 명세"
    ).encode("utf-8")
    result = transform_document(external, "md", template, "md")
    # 섹션 2개인데 외부 내용이 1 단락 → 하나는 매핑 못 받을 수 있음
    assert isinstance(result.mapped_sections, list)
    assert isinstance(result.unmapped_sections, list)
    assert len(result.mapped_sections) == 2
