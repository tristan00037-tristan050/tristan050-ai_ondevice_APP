"""bm25_index.py — 경량 BM25 인덱스 (외부 의존성 없음)."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import NamedTuple

from .chunkers import Chunk

_TOKEN_RE = re.compile(r"[^\s\W]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Result(NamedTuple):
    chunk: Chunk
    score: float


class BM25Index:
    """BM25Okapi 인덱스.

    k1=1.5, b=0.75 (표준 파라미터).
    """

    k1: float = 1.5
    b: float = 0.75

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avgdl: float = 0.0

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        self._tf = []
        self._df = Counter()
        total_len = 0
        for chunk in self._chunks:
            tokens = _tokenize(chunk.text)
            tf = Counter(tokens)
            self._tf.append(tf)
            self._df.update(tf.keys())
            total_len += len(tokens)
        self._avgdl = total_len / max(len(self._chunks), 1)

    def search(self, query: str, top_k: int = 10) -> list[BM25Result]:
        if not self._chunks:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        n = len(self._chunks)
        scores: list[float] = []
        for i, tf in enumerate(self._tf):
            doc_len = sum(tf.values())
            score = 0.0
            for term in q_tokens:
                f = tf.get(term, 0)
                df = self._df.get(term, 0)
                if f == 0 or df == 0:
                    continue
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
                tf_norm = (f * (self.k1 + 1)) / (
                    f + self.k1 * (1 - self.b + self.b * doc_len / self._avgdl)
                )
                score += idf * tf_norm
            scores.append(score)
        ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
        return [
            BM25Result(chunk=self._chunks[i], score=scores[i])
            for i in ranked[:top_k]
            if scores[i] > 0
        ]
