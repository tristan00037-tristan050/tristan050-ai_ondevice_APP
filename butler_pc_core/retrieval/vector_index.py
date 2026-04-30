"""vector_index.py — 경량 TF-IDF 코사인 벡터 인덱스 (외부 의존성 없음).

실제 임베딩 모델이 없을 때의 로컬 폴백 구현.
Phase 4에서 ONNX 임베딩 모델로 교체 예정.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import NamedTuple

from .chunkers import Chunk

_TOKEN_RE = re.compile(r"[^\s\W]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _tfidf_vector(tokens: list[str], df: Counter, n: int) -> dict[str, float]:
    tf = Counter(tokens)
    vec: dict[str, float] = {}
    for term, count in tf.items():
        d = df.get(term, 0)
        if d == 0:
            continue
        idf = math.log((n + 1) / (d + 1)) + 1
        vec[term] = (1 + math.log(count)) * idf
    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(a.get(t, 0.0) * v for t, v in b.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorResult(NamedTuple):
    chunk: Chunk
    score: float


class VectorIndex:
    """TF-IDF 코사인 유사도 인덱스."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: list[dict[str, float]] = []
        self._df: Counter = Counter()

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        token_lists = [_tokenize(c.text) for c in self._chunks]
        self._df = Counter()
        for tokens in token_lists:
            self._df.update(set(tokens))
        n = len(self._chunks)
        self._vectors = [_tfidf_vector(tl, self._df, n) for tl in token_lists]

    def search(self, query: str, top_k: int = 10) -> list[VectorResult]:
        if not self._chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        n = len(self._chunks)
        q_vec = _tfidf_vector(q_tokens, self._df, n)
        if not q_vec:
            return []
        scores = [_cosine(q_vec, v) for v in self._vectors]
        ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
        return [
            VectorResult(chunk=self._chunks[i], score=scores[i])
            for i in ranked[:top_k]
            if scores[i] > 0
        ]
