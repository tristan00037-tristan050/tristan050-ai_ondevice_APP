"""pdf_report_chunker.py — PDF 보고서 청커 (텍스트 추출 후 처리)."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_PAGE_SEP = re.compile(r"\f|\[PAGE\s*\d+\]|--- Page \d+ ---", re.IGNORECASE)
_SECTION_RE = re.compile(r"(?m)^(?:\d+\.\s+|[IVX]+\.\s+)(?P<title>.+)$")


class PdfReportChunker(BaseChunker):
    """PDF 보고서: 폼피드/페이지 마커 → 페이지 경계, 섹션 헤더 우선 분할."""

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        pages = _PAGE_SEP.split(content)
        chunks: list[Chunk] = []
        idx = 0
        for page_num, page_text in enumerate(pages, start=1):
            page_text = page_text.strip()
            if not page_text:
                continue
            sections = _split_by_section(page_text)
            for title, body in sections:
                full = f"{title}\n{body}".strip() if title else body.strip()
                if not full:
                    continue
                if len(full) <= self.MAX_CHUNK_CHARS:
                    chunks.append(Chunk(
                        chunk_id=self._make_id(source_file, idx),
                        text=full,
                        source_file=source_file,
                        page_or_sheet=page_num,
                        section_title=title or None,
                    ))
                    idx += 1
                else:
                    sub = self._split_by_max(full, source_file, offset=idx)
                    for c in sub:
                        c.page_or_sheet = page_num
                        c.section_title = title or None
                    chunks.extend(sub)
                    idx += len(sub)
        return chunks


def _split_by_section(text: str) -> list[tuple[str, str]]:
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return [("", text)]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("", text[: matches[0].start()]))
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((title, text[body_start:body_end]))
    return sections
