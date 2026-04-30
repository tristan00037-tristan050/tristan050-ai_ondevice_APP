"""receipt_chunker.py — 영수증/거래명세서 청커."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_RECEIPT_SEP = re.compile(
    r"(?m)^(?:={3,}|={3,}\s*영수증\s*={3,}|-{3,}\s*RECEIPT\s*-{3,})$",
    re.IGNORECASE,
)
_ITEM_LINE = re.compile(
    r"(?m)^(?P<item>.+?)\s{2,}(?P<qty>\d+)\s{2,}(?P<price>[\d,]+)$"
)


class ReceiptChunker(BaseChunker):
    """영수증: 영수증 1건 = 1청크 (헤더+품목+합계 통합).

    단일 영수증 내 품목이 MAX_CHUNK_CHARS 초과 시 품목 N개씩 재분할.
    """

    ITEMS_PER_CHUNK: int = 20

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        receipts = [r.strip() for r in _RECEIPT_SEP.split(content) if r.strip()]
        if not receipts:
            receipts = [content.strip()]
        chunks: list[Chunk] = []
        idx = 0
        for receipt_num, receipt_text in enumerate(receipts, start=1):
            if not receipt_text:
                continue
            if len(receipt_text) <= self.MAX_CHUNK_CHARS:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=receipt_text,
                    source_file=source_file,
                    page_or_sheet=receipt_num,
                    section_title=f"영수증_{receipt_num}",
                    metadata={"receipt_num": receipt_num},
                ))
                idx += 1
            else:
                header, items, footer = _parse_receipt_sections(receipt_text)
                step = self.ITEMS_PER_CHUNK
                for batch_start in range(0, max(len(items), 1), step):
                    batch = items[batch_start: batch_start + step]
                    parts = [header] + batch + ([footer] if batch_start + step >= len(items) and footer else [])
                    text = "\n".join(p for p in parts if p).strip()
                    if not text:
                        continue
                    chunks.append(Chunk(
                        chunk_id=self._make_id(source_file, idx),
                        text=text,
                        source_file=source_file,
                        page_or_sheet=receipt_num,
                        section_title=f"영수증_{receipt_num}",
                        metadata={"receipt_num": receipt_num, "item_batch": batch_start // step},
                    ))
                    idx += 1
        return chunks


def _parse_receipt_sections(text: str) -> tuple[str, list[str], str]:
    lines = text.splitlines()
    header_lines: list[str] = []
    item_lines: list[str] = []
    footer_lines: list[str] = []
    state = "header"
    for line in lines:
        if state == "header" and _ITEM_LINE.match(line):
            state = "items"
        if state == "items" and not _ITEM_LINE.match(line) and line.strip():
            state = "footer"
        if state == "header":
            header_lines.append(line)
        elif state == "items":
            item_lines.append(line)
        else:
            footer_lines.append(line)
    return "\n".join(header_lines), item_lines, "\n".join(footer_lines)
