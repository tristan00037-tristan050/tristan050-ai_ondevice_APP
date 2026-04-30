"""meeting_minutes_chunker.py — 회의록 파일 청커."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_AGENDA_RE = re.compile(
    r"(?m)^(?:#{1,3}\s+|[●◎■□▶▷►]\s*|(?:\d+[\.\)]\s+)|(?:[가-힣]\.\s+))"
    r"(?P<title>.+)$"
)


class MeetingMinutesChunker(BaseChunker):
    """회의록: 안건(##/번호/특수기호) 경계로 분할, 초과 시 MAX_CHUNK_CHARS 재분할."""

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        sections = _split_by_agenda(content)
        chunks: list[Chunk] = []
        idx = 0
        for title, body in sections:
            full = f"{title}\n{body}".strip() if title else body.strip()
            if not full:
                continue
            if len(full) <= self.MAX_CHUNK_CHARS:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=full,
                    source_file=source_file,
                    section_title=title or None,
                ))
                idx += 1
            else:
                sub = self._split_by_max(full, source_file, offset=idx)
                for c in sub:
                    c.section_title = title or None
                chunks.extend(sub)
                idx += len(sub)
        return chunks


def _split_by_agenda(content: str) -> list[tuple[str, str]]:
    matches = list(_AGENDA_RE.finditer(content))
    if not matches:
        return [("", content)]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("", content[: matches[0].start()]))
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((title, content[body_start:body_end]))
    return sections
