"""retrieval_cache.py — 검색 결과 캐시 (TTL 7일)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseCache, _DEFAULT_DB

_TTL_7D = 7 * 24 * 3600


class RetrievalCache(BaseCache):
    """
    키: sha256(query_normalized) + index_version + top_k + filters_hash
    TTL: 7일
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        super().__init__(
            table="retrieval",
            db_path=db_path,
            ttl_seconds=_TTL_7D,
        )

    def build_key(
        self,
        *,
        query_normalized: str,
        index_version: str,
        top_k: int,
        filters: Optional[Dict] = None,
    ) -> str:
        q_hash = hashlib.sha256(query_normalized.lower().strip().encode()).hexdigest()
        f_hash = hashlib.sha256(
            json.dumps(filters or {}, sort_keys=True).encode()
        ).hexdigest()[:16]
        return f"{q_hash}:{index_version}:{top_k}:{f_hash}"

    def get_results(
        self,
        query_normalized: str,
        index_version: str,
        top_k: int,
        filters: Optional[Dict] = None,
    ) -> Optional[List[Dict]]:
        return self.get(
            self.build_key(
                query_normalized=query_normalized,
                index_version=index_version,
                top_k=top_k,
                filters=filters,
            )
        )

    def set_results(
        self,
        query_normalized: str,
        results: List[Dict],
        index_version: str,
        top_k: int,
        filters: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.set(
            self.build_key(
                query_normalized=query_normalized,
                index_version=index_version,
                top_k=top_k,
                filters=filters,
            ),
            results,
            ttl_seconds=ttl_seconds,
        )
