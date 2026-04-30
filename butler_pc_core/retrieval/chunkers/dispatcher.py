"""dispatcher.py — 파일 확장자/유형으로 적절한 청커를 선택."""
from __future__ import annotations

from pathlib import Path

from .base import BaseChunker
from .docx_chunker import DocxChunker
from .email_chunker import EmailChunker
from .meeting_minutes_chunker import MeetingMinutesChunker
from .pdf_report_chunker import PdfReportChunker
from .ppt_chunker import PptChunker
from .receipt_chunker import ReceiptChunker
from .xlsx_chunker import XlsxChunker

_EXT_MAP: dict[str, type[BaseChunker]] = {
    ".pdf": PdfReportChunker,
    ".docx": DocxChunker,
    ".doc": DocxChunker,
    ".xlsx": XlsxChunker,
    ".xls": XlsxChunker,
    ".csv": XlsxChunker,
    ".pptx": PptChunker,
    ".ppt": PptChunker,
    ".eml": EmailChunker,
    ".msg": EmailChunker,
}

_TYPE_MAP: dict[str, type[BaseChunker]] = {
    "meeting_minutes": MeetingMinutesChunker,
    "pdf_report": PdfReportChunker,
    "docx": DocxChunker,
    "xlsx": XlsxChunker,
    "email": EmailChunker,
    "ppt": PptChunker,
    "receipt": ReceiptChunker,
}


def get_chunker(file_path: str | Path | None = None, file_type: str | None = None) -> BaseChunker:
    """파일 경로 또는 유형 문자열로 청커를 반환.

    우선순위: file_type > 확장자 > MeetingMinutesChunker(기본)
    """
    if file_type and file_type in _TYPE_MAP:
        return _TYPE_MAP[file_type]()
    if file_path:
        ext = Path(file_path).suffix.lower()
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]()
    return MeetingMinutesChunker()
