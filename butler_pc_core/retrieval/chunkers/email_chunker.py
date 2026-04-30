"""email_chunker.py — 이메일 청커."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_HEADER_FIELDS = re.compile(
    r"(?im)^(?:From|To|Cc|Bcc|Subject|Date|Reply-To)\s*:.*$"
)
_QUOTED_LINES = re.compile(r"(?m)^>.*$")
_THREAD_SEP = re.compile(
    r"(?m)^-{5,}\s*(?:Original Message|Forwarded message|원본 메시지|전달된 메시지)"
    r"\s*-{5,}$",
    re.IGNORECASE,
)


class EmailChunker(BaseChunker):
    """이메일: 헤더 1청크 + 본문 1청크 + 인용/스레드 별도 청크.

    인용 블록은 별도 청크로 분리 (검색 노이즈 방지).
    스레드 구분선 이후는 재귀적으로 동일 처리.
    """

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        parts = _THREAD_SEP.split(content)
        chunks: list[Chunk] = []
        idx = 0
        for part_num, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            header_lines = _HEADER_FIELDS.findall(part)
            header_text = "\n".join(header_lines).strip()
            body = _HEADER_FIELDS.sub("", part).strip()

            if header_text:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=header_text,
                    source_file=source_file,
                    section_title="header",
                    metadata={"email_part": part_num, "type": "header"},
                ))
                idx += 1

            quoted = "\n".join(_QUOTED_LINES.findall(body)).strip()
            clean_body = _QUOTED_LINES.sub("", body).strip()

            if clean_body:
                for c in self._split_by_max(clean_body, source_file, offset=idx):
                    c.section_title = "body"
                    c.metadata = {"email_part": part_num, "type": "body"}
                    chunks.append(c)
                    idx += 1

            if quoted:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=quoted,
                    source_file=source_file,
                    section_title="quoted",
                    metadata={"email_part": part_num, "type": "quoted"},
                ))
                idx += 1

        return chunks
