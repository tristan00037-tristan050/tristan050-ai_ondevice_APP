"""ppt_chunker.py — PowerPoint/프레젠테이션 청커."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_SLIDE_SEP = re.compile(
    r"(?m)^(?:=== Slide\s*(?P<num>\d+)\s*===|--- Slide\s*(?P<num2>\d+)\s*---)",
    re.IGNORECASE,
)


class PptChunker(BaseChunker):
    """PPT: 슬라이드 단위 1청크 (제목+본문 노트 포함), 초과 시 재분할.

    입력 형식:
      === Slide 1 ===
      [Title] 슬라이드 제목
      [Body] 본문 내용...
      [Notes] 발표자 노트...
    """

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        slides = _split_slides(content)
        chunks: list[Chunk] = []
        idx = 0
        for slide_num, slide_text in slides:
            slide_text = slide_text.strip()
            if not slide_text:
                continue
            title = _extract_slide_title(slide_text)
            if len(slide_text) <= self.MAX_CHUNK_CHARS:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=slide_text,
                    source_file=source_file,
                    page_or_sheet=slide_num,
                    section_title=title,
                ))
                idx += 1
            else:
                sub = self._split_by_max(slide_text, source_file, offset=idx)
                for c in sub:
                    c.page_or_sheet = slide_num
                    c.section_title = title
                chunks.extend(sub)
                idx += len(sub)
        return chunks


def _split_slides(content: str) -> list[tuple[int, str]]:
    matches = list(_SLIDE_SEP.finditer(content))
    if not matches:
        return [(1, content)]
    slides: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        num_str = m.group("num") or m.group("num2") or str(i + 1)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        slides.append((int(num_str), content[body_start:body_end]))
    return slides


def _extract_slide_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[Title]"):
            return line[len("[Title]"):].strip() or None
        if line and not line.startswith("["):
            return line[:80]
    return None
