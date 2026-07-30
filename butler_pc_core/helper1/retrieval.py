"""Typed BM25 + dense retrieval with reciprocal-rank fusion."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .contracts import (
    EncoderIdentity,
    Helper1ContractError,
    RetrievedChunk,
    assert_same_space,
    canonical_json,
    sha256_bytes,
)
from .index_store import LoadedIndex
from .ingestion import Chunk

TOKENIZER_VERSION = "unicode-nfkc-word-v2"
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
RRF_K = 60


class RetrievalError(RuntimeError):
    pass


class EmbeddingBackend(Protocol):
    @property
    def identity(self) -> EncoderIdentity: ...

    def encode_documents(
        self, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]: ...

    def encode_query(self, text: str) -> tuple[float, ...]: ...


def tokenize(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value)
    tokens = []
    for match in TOKEN_RE.finditer(normalized):
        token = match.group(0)
        if token.isascii():
            token = token.casefold()
        if len(token) <= 128:
            tokens.append(token)
    return tuple(tokens)


def lexical_tokenizer_sha256() -> str:
    return sha256_bytes(
        canonical_json(
            {
                "version": TOKENIZER_VERSION,
                "normalization": "NFKC",
                "pattern": TOKEN_RE.pattern,
                "ascii_casefold": True,
                "max_token_chars": 128,
            }
        )
    )


def build_lexical_index(chunks: tuple[Chunk, ...]) -> dict[str, Any]:
    if not chunks:
        raise RetrievalError("LEXICAL_CHUNKS_EMPTY")
    lengths: list[int] = []
    postings: dict[str, list[list[int]]] = {}
    for row, chunk in enumerate(chunks):
        counts = Counter(tokenize(chunk.text))
        lengths.append(sum(counts.values()))
        for term, frequency in sorted(counts.items()):
            postings.setdefault(term, []).append([row, frequency])
    if not postings:
        raise RetrievalError("LEXICAL_TERMS_EMPTY")
    terms = {
        term: {"df": len(rows), "postings": rows}
        for term, rows in sorted(postings.items())
    }
    return {
        "schema_version": "butler.helper1.lexical.v2",
        "tokenizer_sha256": lexical_tokenizer_sha256(),
        "document_count": len(chunks),
        "document_lengths": lengths,
        "average_document_length": sum(lengths) / len(lengths),
        "terms": terms,
    }


def validate_lexical_index(value: Mapping[str, Any], chunk_count: int) -> None:
    if set(value) != {
        "schema_version",
        "tokenizer_sha256",
        "document_count",
        "document_lengths",
        "average_document_length",
        "terms",
    }:
        raise RetrievalError("LEXICAL_FIELDS_INVALID")
    if (
        value.get("schema_version") != "butler.helper1.lexical.v2"
        or value.get("tokenizer_sha256") != lexical_tokenizer_sha256()
        or value.get("document_count") != chunk_count
    ):
        raise RetrievalError("LEXICAL_IDENTITY_INVALID")
    lengths = value.get("document_lengths")
    average = value.get("average_document_length")
    terms = value.get("terms")
    if (
        not isinstance(lengths, list)
        or len(lengths) != chunk_count
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in lengths
        )
        or isinstance(average, bool)
        or not isinstance(average, (int, float))
        or not math.isfinite(float(average))
        or float(average) < 0
        or not isinstance(terms, dict)
        or not terms
    ):
        raise RetrievalError("LEXICAL_SHAPE_INVALID")
    for term, record in terms.items():
        if not isinstance(term, str) or not term or len(term) > 128:
            raise RetrievalError("LEXICAL_TERM_INVALID")
        if not isinstance(record, dict) or set(record) != {"df", "postings"}:
            raise RetrievalError("LEXICAL_POSTINGS_INVALID")
        rows = record.get("postings")
        if (
            isinstance(record.get("df"), bool)
            or not isinstance(record.get("df"), int)
            or not isinstance(rows, list)
            or record["df"] != len(rows)
        ):
            raise RetrievalError("LEXICAL_DF_INVALID")
        previous = -1
        for item in rows:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or any(isinstance(part, bool) or not isinstance(part, int) for part in item)
                or item[0] <= previous
                or item[0] < 0
                or item[0] >= chunk_count
                or item[1] < 1
            ):
                raise RetrievalError("LEXICAL_POSTING_INVALID")
            previous = item[0]


def bm25_scores(
    query: str,
    lexical_index: Mapping[str, Any],
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> dict[int, float]:
    count = lexical_index["document_count"]
    lengths = lexical_index["document_lengths"]
    average = max(float(lexical_index["average_document_length"]), 1.0)
    terms = lexical_index["terms"]
    scores: dict[int, float] = {}
    for term in set(tokenize(query)):
        record = terms.get(term)
        if not isinstance(record, dict):
            continue
        df = record["df"]
        inverse = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
        for row, frequency in record["postings"]:
            length_norm = k1 * (1.0 - b + b * lengths[row] / average)
            score = inverse * (frequency * (k1 + 1.0)) / (frequency + length_norm)
            scores[row] = scores.get(row, 0.0) + score
    return scores


def _validate_query_vector(vector: tuple[float, ...], dimension: int) -> None:
    if len(vector) != dimension:
        raise RetrievalError("QUERY_EMBEDDING_DIMENSION_MISMATCH")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in vector
    ):
        raise RetrievalError("QUERY_EMBEDDING_NONFINITE")
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if norm <= 0.0:
        raise RetrievalError("QUERY_EMBEDDING_ZERO_NORM")


def dense_scores(
    query_vector: tuple[float, ...],
    embeddings: tuple[tuple[float, ...], ...],
) -> dict[int, float]:
    return {
        row: sum(float(left) * float(right) for left, right in zip(query_vector, vector))
        for row, vector in enumerate(embeddings)
    }


@dataclass(frozen=True)
class HybridRetriever:
    dense_candidates: int = 50
    lexical_candidates: int = 50

    def __post_init__(self) -> None:
        for value in (self.dense_candidates, self.lexical_candidates):
            if isinstance(value, bool) or not 1 <= value <= 1000:
                raise RetrievalError("RETRIEVAL_CANDIDATE_LIMIT_INVALID")

    def search(
        self,
        *,
        query: str,
        index: LoadedIndex,
        embedder: EmbeddingBackend,
        top_k: int,
    ) -> tuple[RetrievedChunk, ...]:
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise RetrievalError("QUERY_INVALID")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
            raise RetrievalError("TOP_K_INVALID")
        assert_same_space(index.manifest.encoder, embedder.identity)
        validate_lexical_index(index.lexical_index, len(index.chunks))
        query_vector = embedder.encode_query(query)
        _validate_query_vector(query_vector, index.manifest.embedding_dimension)
        dense = dense_scores(query_vector, index.embeddings)
        lexical = bm25_scores(query, index.lexical_index)
        dense_rank = sorted(dense, key=lambda row: (-dense[row], row))[
            : self.dense_candidates
        ]
        lexical_rank = sorted(lexical, key=lambda row: (-lexical[row], row))[
            : self.lexical_candidates
        ]
        fused: dict[int, float] = {}
        for rank, row in enumerate(dense_rank, start=1):
            fused[row] = fused.get(row, 0.0) + 1.0 / (RRF_K + rank)
        for rank, row in enumerate(lexical_rank, start=1):
            fused[row] = fused.get(row, 0.0) + 1.0 / (RRF_K + rank)
        ordered = sorted(fused, key=lambda row: (-fused[row], row))[:top_k]
        results = []
        for row in ordered:
            chunk = index.chunks[row]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    text=chunk.text,
                    dense_score=dense.get(row),
                    lexical_score=lexical.get(row),
                    fused_score=fused[row],
                    generation_id=index.manifest.generation_id,
                    content_sha256=chunk.content_sha256,
                )
            )
        return tuple(results)
