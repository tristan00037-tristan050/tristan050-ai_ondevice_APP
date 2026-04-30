"""lightweight_reranker.py — 경량 크로스인코더 재랭킹 (쿼리-청크 쌍 유사도).

실제 Cross-Encoder 모델이 없을 때의 키워드 기반 폴백 구현.
Phase 4에서 ONNX 크로스인코더로 교체 예정.
"""
from __future__ import annotations

import re
import time
from collections import Counter

from .chunkers import Chunk
from .rrf_fusion import RRFResult

_TOKEN_RE = re.compile(r"[^\s\W]+", re.UNICODE)


def _overlap_score(query_tokens: Counter, text: str) -> float:
    """쿼리 토큰과 텍스트의 단순 겹침 비율."""
    text_tokens = Counter(t.lower() for t in _TOKEN_RE.findall(text))
    common = sum(min(query_tokens[t], text_tokens[t]) for t in query_tokens)
    denom = max(sum(query_tokens.values()), 1)
    return common / denom


def rerank(
    query: str,
    results: list[RRFResult],
    top_k: int = 5,
    timeout_secs: float = 2.0,
) -> list[RRFResult]:
    """재랭킹 적용.

    timeout_secs 내에 완료되지 않으면 입력 results[:top_k]를 그대로 반환 (폴백).
    """
    if not results:
        return []
    deadline = time.monotonic() + timeout_secs
    q_tokens = Counter(t.lower() for t in _TOKEN_RE.findall(query))
    if not q_tokens:
        return results[:top_k]

    scored: list[tuple[float, RRFResult]] = []
    for r in results:
        if time.monotonic() > deadline:
            return results[:top_k]
        s = _overlap_score(q_tokens, r.chunk.text)
        scored.append((r.rrf_score + s * 0.1, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]
