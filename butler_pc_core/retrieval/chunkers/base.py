"""base.py — 청커 추상 베이스 + Chunk 데이터클래스."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """단일 청크 단위."""
    chunk_id: str
    text: str
    source_file: str
    page_or_sheet: int | None = None
    section_title: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("Chunk.text must not be empty")
        if not self.chunk_id:
            raise ValueError("Chunk.chunk_id must not be empty")


class BaseChunker(ABC):
    """모든 파일 유형 청커의 공통 인터페이스."""

    MAX_CHUNK_CHARS: int = 1200
    OVERLAP_CHARS: int = 100

    @abstractmethod
    def chunk(self, content: str, source_file: str = "") -> list[Chunk]:
        """content를 Chunk 리스트로 분할한다."""

    def _make_id(self, source_file: str, index: int) -> str:
        base = source_file.replace("/", "_").replace("\\", "_") or "doc"
        return f"{base}__chunk_{index:04d}"

    def _split_by_max(self, text: str, source_file: str, offset: int = 0) -> list[Chunk]:
        """MAX_CHUNK_CHARS 단위로 단순 분할 (공통 유틸)."""
        chunks: list[Chunk] = []
        step = self.MAX_CHUNK_CHARS - self.OVERLAP_CHARS
        i = 0
        idx = offset
        while i < len(text):
            end = min(i + self.MAX_CHUNK_CHARS, len(text))
            segment = text[i:end].strip()
            if segment:
                chunks.append(Chunk(
                    chunk_id=self._make_id(source_file, idx),
                    text=segment,
                    source_file=source_file,
                    start_char=i,
                    end_char=end,
                ))
                idx += 1
            i += step
        return chunks
