"""document_text_cache.py — 파일 텍스트 추출 캐시 (TTL 30일)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from .base import BaseCache, _DEFAULT_DB

_TTL_30D = 30 * 24 * 3600


class DocumentTextCache(BaseCache):
    """
    키: sha256(file_bytes) + parser_version
    TTL: 30일
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        super().__init__(
            table="document_text",
            db_path=db_path,
            ttl_seconds=_TTL_30D,
        )

    def build_key(self, *, file_bytes: bytes, parser_version: str = "v1") -> str:
        digest = hashlib.sha256(file_bytes).hexdigest()
        return f"{digest}:{parser_version}"

    # 편의 메서드
    def get_text(self, file_bytes: bytes, parser_version: str = "v1") -> Optional[str]:
        return self.get(self.build_key(file_bytes=file_bytes, parser_version=parser_version))

    def set_text(
        self,
        file_bytes: bytes,
        text: str,
        parser_version: str = "v1",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.set(
            self.build_key(file_bytes=file_bytes, parser_version=parser_version),
            text,
            ttl_seconds=ttl_seconds,
        )
