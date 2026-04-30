"""chunk_embedding_cache.py — 청크 임베딩 캐시 (TTL 90일)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, List, Optional

from .base import BaseCache, _DEFAULT_DB

_TTL_90D = 90 * 24 * 3600


class ChunkEmbeddingCache(BaseCache):
    """
    키: sha256(chunk_text) + embedding_model_id + tokenizer_version
    TTL: 90일
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        super().__init__(
            table="chunk_embedding",
            db_path=db_path,
            ttl_seconds=_TTL_90D,
        )

    def build_key(
        self,
        *,
        chunk_text: str,
        embedding_model_id: str,
        tokenizer_version: str = "v1",
    ) -> str:
        digest = hashlib.sha256(chunk_text.encode()).hexdigest()
        return f"{digest}:{embedding_model_id}:{tokenizer_version}"

    def get_embedding(
        self,
        chunk_text: str,
        embedding_model_id: str,
        tokenizer_version: str = "v1",
    ) -> Optional[List[float]]:
        return self.get(
            self.build_key(
                chunk_text=chunk_text,
                embedding_model_id=embedding_model_id,
                tokenizer_version=tokenizer_version,
            )
        )

    def set_embedding(
        self,
        chunk_text: str,
        embedding: List[float],
        embedding_model_id: str,
        tokenizer_version: str = "v1",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.set(
            self.build_key(
                chunk_text=chunk_text,
                embedding_model_id=embedding_model_id,
                tokenizer_version=tokenizer_version,
            ),
            embedding,
            ttl_seconds=ttl_seconds,
        )
