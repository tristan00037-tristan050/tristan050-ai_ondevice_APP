"""pipeline.py — Personal Pack 하이브리드 검색 파이프라인 v2."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .bm25_index import BM25Index
from .chunkers import Chunk
from .lightweight_reranker import rerank
from .metadata_booster import boost
from .rrf_fusion import RRFResult, reciprocal_rank_fusion
from .vector_index import VectorIndex


@dataclass
class RetrievalResult:
    chunk: Chunk
    rrf_score: float
    bm25_rank: int | None
    vector_rank: int | None
    final_rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersonalPackIndex:
    """빌드된 BM25 + Vector 인덱스 쌍."""
    bm25: BM25Index
    vector: VectorIndex
    chunks: list[Chunk]

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "PersonalPackIndex":
        bm25 = BM25Index()
        bm25.build(chunks)
        vec = VectorIndex()
        vec.build(chunks)
        return cls(bm25=bm25, vector=vec, chunks=list(chunks))


class HybridRetrievalPipeline:
    """BM25 + Vector + RRF + MetadataBoost + LightweightReranker.

    사용법:
        index = PersonalPackIndex.build(chunks)
        pipeline = HybridRetrievalPipeline(index)
        results = pipeline.retrieve("쿼리", top_k=5)
    """

    def __init__(
        self,
        index: PersonalPackIndex,
        factpack_ids: frozenset[str] | None = None,
        reranker_timeout_secs: float = 2.0,
    ) -> None:
        self._index = index
        self._factpack_ids = factpack_ids or frozenset()
        self._reranker_timeout = reranker_timeout_secs

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        now: datetime | None = None,
    ) -> list[RetrievalResult]:
        if not query or not query.strip():
            return []

        fetch_k = max(top_k * 3, 20)

        bm25_raw = self._index.bm25.search(query, top_k=fetch_k)
        vec_raw = self._index.vector.search(query, top_k=fetch_k)

        fused = reciprocal_rank_fusion(
            [(r.chunk, r.score) for r in bm25_raw],
            [(r.chunk, r.score) for r in vec_raw],
            top_k=fetch_k,
        )

        boosted = boost(
            fused,
            factpack_ids=self._factpack_ids if self._factpack_ids else None,
            now=now,
        )

        reranked = rerank(
            query,
            boosted,
            top_k=top_k,
            timeout_secs=self._reranker_timeout,
        )

        return [
            RetrievalResult(
                chunk=r.chunk,
                rrf_score=r.rrf_score,
                bm25_rank=r.bm25_rank,
                vector_rank=r.vector_rank,
                final_rank=i + 1,
            )
            for i, r in enumerate(reranked)
        ]
