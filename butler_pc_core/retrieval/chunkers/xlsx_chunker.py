"""xlsx_chunker.py — 엑셀/스프레드시트 청커 (TSV/CSV 텍스트 변환 후 처리)."""
from __future__ import annotations

import re

from .base import BaseChunker, Chunk

_SHEET_SEP = re.compile(r"=== Sheet:\s*(?P<name>[^\n]+) ===")


class XlsxChunker(BaseChunker):
    """XLSX: 시트 단위 분할 → 행 N개씩 묶어 청크.

    입력 형식 (텍스트 변환 후):
      === Sheet: 시트명 ===
      헤더행\t열1\t열2...
      데이터행\t...
    """

    ROWS_PER_CHUNK: int = 30

    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        sheets = _split_sheets(content)
        chunks: list[Chunk] = []
        idx = 0
        for sheet_num, (sheet_name, sheet_text) in enumerate(sheets, start=1):
            lines = [l for l in sheet_text.splitlines() if l.strip()]
            if not lines:
                continue
            header = lines[0]
            data_lines = lines[1:]
            step = self.ROWS_PER_CHUNK
            for batch_start in range(0, max(len(data_lines), 1), step):
                batch = data_lines[batch_start: batch_start + step]
                text = header + "\n" + "\n".join(batch) if batch else header
                text = text.strip()
                if not text:
                    continue
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=text,
                    source_file=source_file,
                    page_or_sheet=sheet_num,
                    section_title=sheet_name or None,
                    metadata={"sheet_name": sheet_name, "row_start": batch_start + 1},
                ))
                idx += 1
        return chunks


def _split_sheets(content: str) -> list[tuple[str, str]]:
    matches = list(_SHEET_SEP.finditer(content))
    if not matches:
        return [("Sheet1", content)]
    sheets: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        name = m.group("name").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sheets.append((name, content[body_start:body_end]))
    return sheets
