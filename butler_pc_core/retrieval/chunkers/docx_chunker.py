"""docx_chunker.py — Word 문서 청커 (텍스트 변환 후 처리)."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_HEADING_RE = re.compile(
    r"(?m)^(?:#{1,4}\s+|HEADING\d?\s*:\s*)(?P<title>.+)$", re.IGNORECASE
)
_BLANK_LINES = re.compile(r"\n{3,}")


class DocxChunker(BaseChunker):
    """DOCX: Heading 태그 or # 기준으로 분할, 빈 줄 3개 이상을 단락 구분으로 사용."""

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        content = _BLANK_LINES.sub("\n\n", content)
        sections = _split_by_heading(content)
        chunks: list[Chunk] = []
        idx = 0
        for title, body in sections:
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            buffer = f"{title}\n" if title else ""
            for para in paragraphs:
                candidate = (buffer + para).strip()
                if len(candidate) > self.MAX_CHUNK_CHARS:
                    if buffer.strip():
                        chunks.append(Chunk(
                            chunk_id=self._make_id(source_file, idx),
                            text=buffer.strip(),
                            source_file=source_file,
                            section_title=title or None,
                        ))
                        idx += 1
                        buffer = ""
                    sub = self._split_by_max(para, source_file, offset=idx)
                    for c in sub:
                        c.section_title = title or None
                    chunks.extend(sub)
                    idx += len(sub)
                else:
                    buffer = candidate + "\n\n"
            if buffer.strip():
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=buffer.strip(),
                    source_file=source_file,
                    section_title=title or None,
                ))
                idx += 1
        return chunks


def _split_by_heading(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(text))
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
