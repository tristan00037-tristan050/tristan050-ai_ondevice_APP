"""rrf_fusion.py — Reciprocal Rank Fusion."""
from __future__ import annotations

from typing import NamedTuple

from .chunkers import Chunk

_RRF_K = 60


class RRFResult(NamedTuple):
    chunk: Chunk
    rrf_score: float
    bm25_rank: int | None
    vector_rank: int | None


def reciprocal_rank_fusion(
    bm25_results: list[tuple[Chunk, float]],
    vector_results: list[tuple[Chunk, float]],
    top_k: int = 10,
    k: int = _RRF_K,
) -> list[RRFResult]:
    """두 랭킹 리스트를 RRF로 통합한다.

    score = sum(1 / (k + rank)) over all lists where the chunk appears.
    """
    bm25_rank_map = {c.chunk_id: (i + 1) for i, (c, _) in enumerate(bm25_results)}
    vec_rank_map = {c.chunk_id: (i + 1) for i, (c, _) in enumerate(vector_results)}
    chunk_map: dict[str, Chunk] = {}
    for c, _ in bm25_results:
        chunk_map[c.chunk_id] = c
    for c, _ in vector_results:
        chunk_map[c.chunk_id] = c

    all_ids = set(bm25_rank_map) | set(vec_rank_map)
    scored: list[tuple[str, float]] = []
    for cid in all_ids:
        score = 0.0
        if cid in bm25_rank_map:
            score += 1.0 / (k + bm25_rank_map[cid])
        if cid in vec_rank_map:
            score += 1.0 / (k + vec_rank_map[cid])
        scored.append((cid, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        RRFResult(
            chunk=chunk_map[cid],
            rrf_score=score,
            bm25_rank=bm25_rank_map.get(cid),
            vector_rank=vec_rank_map.get(cid),
        )
        for cid, score in scored[:top_k]
    ]
