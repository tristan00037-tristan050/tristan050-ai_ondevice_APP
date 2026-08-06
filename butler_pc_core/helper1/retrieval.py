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
    RetrievalTraceHitV2,
    assert_same_space,
    canonical_json,
    require_digest,
    require_finite,
    require_int,
    sha256_bytes,
)
from .index_store import LoadedIndex
from .ingestion import Chunk

TOKENIZER_VERSION = "unicode-nfkc-word-v2"
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


class RetrievalError(RuntimeError):
    pass


class EmbeddingBackend(Protocol):
    @property
    def identity(self) -> EncoderIdentity: ...

    def encode_documents(
        self, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]: ...

    def encode_query(self, text: str) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """Immutable retrieval constants and protected calibration identity.

    ``DEVELOPMENT_UNCALIBRATED`` is deliberately useful for unit tests and
    local algorithm work, but the product composition root rejects it.  A
    production policy is data issued by the protected calibration workflow;
    code defaults can therefore never silently become an approval threshold.
    """

    dense_candidates: int = 50
    lexical_candidates: int = 50
    rrf_k: int = 60
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    calibration_state: str = "DEVELOPMENT_UNCALIBRATED"
    corpus_sha256: str | None = None
    evaluator_sha256: str | None = None
    threshold_policy_sha256: str | None = None
    approval_receipt_sha256: str | None = None
    schema_version: str = "butler.helper1.retrieval-policy.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.retrieval-policy.v1":
            raise RetrievalError("RETRIEVAL_POLICY_SCHEMA_INVALID")
        require_int(
            self.dense_candidates,
            minimum=1,
            maximum=1000,
            code="RETRIEVAL_CANDIDATE_LIMIT_INVALID",
        )
        require_int(
            self.lexical_candidates,
            minimum=1,
            maximum=1000,
            code="RETRIEVAL_CANDIDATE_LIMIT_INVALID",
        )
        require_int(self.rrf_k, minimum=1, maximum=100_000, code="RRF_K_INVALID")
        k1 = require_finite(self.bm25_k1, "BM25_K1_INVALID")
        b = require_finite(self.bm25_b, "BM25_B_INVALID")
        if k1 <= 0.0 or not 0.0 <= b <= 1.0:
            raise RetrievalError("BM25_POLICY_INVALID")
        if self.calibration_state not in {
            "DEVELOPMENT_UNCALIBRATED",
            "APPROVED",
        }:
            raise RetrievalError("RETRIEVAL_CALIBRATION_STATE_INVALID")
        identities = (
            self.corpus_sha256,
            self.evaluator_sha256,
            self.threshold_policy_sha256,
            self.approval_receipt_sha256,
        )
        if self.calibration_state == "APPROVED":
            if any(value is None for value in identities):
                raise RetrievalError("BLOCK_RETRIEVAL_POLICY_UNCALIBRATED")
            for value in identities:
                require_digest(value, "RETRIEVAL_CALIBRATION_DIGEST_INVALID")
        elif any(value is not None for value in identities):
            raise RetrievalError("RETRIEVAL_UNAPPROVED_IDENTITY_PRESENT")

    @property
    def is_calibrated(self) -> bool:
        return self.calibration_state == "APPROVED"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dense_candidates": self.dense_candidates,
            "lexical_candidates": self.lexical_candidates,
            "rrf_k": self.rrf_k,
            "bm25_k1": self.bm25_k1,
            "bm25_b": self.bm25_b,
            "calibration_state": self.calibration_state,
            "corpus_sha256": self.corpus_sha256,
            "evaluator_sha256": self.evaluator_sha256,
            "threshold_policy_sha256": self.threshold_policy_sha256,
            "approval_receipt_sha256": self.approval_receipt_sha256,
        }

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


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
    policy: RetrievalPolicy = RetrievalPolicy()

    def __post_init__(self) -> None:
        if type(self.policy) is not RetrievalPolicy:
            raise RetrievalError("RETRIEVAL_POLICY_INVALID")

    def search(
        self,
        *,
        query: str,
        index: LoadedIndex,
        embedder: EmbeddingBackend,
        top_k: int,
    ) -> tuple[RetrievedChunk, ...]:
        chunks, _trace = self.search_with_trace(
            query=query,
            index=index,
            embedder=embedder,
            top_k=top_k,
            expected_workspace_id=index.manifest.workspace_id,
            expected_generation_id=index.manifest.generation_id,
        )
        return chunks

    def search_with_trace(
        self,
        *,
        query: str,
        index: LoadedIndex,
        embedder: EmbeddingBackend,
        top_k: int,
        expected_workspace_id: str,
        expected_generation_id: str,
    ) -> tuple[tuple[RetrievedChunk, ...], tuple[RetrievalTraceHitV2, ...]]:
        """Search one verified generation and emit an exact deterministic trace."""
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise RetrievalError("QUERY_INVALID")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
            raise RetrievalError("TOP_K_INVALID")
        if index.manifest.workspace_id != expected_workspace_id:
            raise RetrievalError("WRONG_WORKSPACE_LEAKAGE")
        if index.manifest.generation_id != expected_generation_id:
            raise RetrievalError("STALE_GENERATION_LEAKAGE")
        assert_same_space(index.manifest.encoder, embedder.identity)
        validate_lexical_index(index.lexical_index, len(index.chunks))
        query_vector = embedder.encode_query(query)
        _validate_query_vector(query_vector, index.manifest.embedding_dimension)
        dense = dense_scores(query_vector, index.embeddings)
        lexical = bm25_scores(
            query,
            index.lexical_index,
            k1=self.policy.bm25_k1,
            b=self.policy.bm25_b,
        )
        stable_key = lambda row: (index.chunks[row].source_id, index.chunks[row].chunk_id)
        dense_rank = sorted(dense, key=lambda row: (-dense[row], stable_key(row)))[
            : self.policy.dense_candidates
        ]
        lexical_rank = sorted(lexical, key=lambda row: (-lexical[row], stable_key(row)))[
            : self.policy.lexical_candidates
        ]
        dense_positions = {row: rank for rank, row in enumerate(dense_rank, start=1)}
        lexical_positions = {
            row: rank for rank, row in enumerate(lexical_rank, start=1)
        }
        fused: dict[int, float] = {}
        for rank, row in enumerate(dense_rank, start=1):
            fused[row] = fused.get(row, 0.0) + 1.0 / (self.policy.rrf_k + rank)
        for rank, row in enumerate(lexical_rank, start=1):
            fused[row] = fused.get(row, 0.0) + 1.0 / (self.policy.rrf_k + rank)
        ordered = sorted(fused, key=lambda row: (-fused[row], stable_key(row)))[:top_k]
        results: list[RetrievedChunk] = []
        traces: list[RetrievalTraceHitV2] = []
        for fused_rank, row in enumerate(ordered, start=1):
            chunk = index.chunks[row]
            chunk_bytes = chunk.text.encode("utf-8")
            result = RetrievedChunk(
                workspace_id=index.manifest.workspace_id,
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                text=chunk.text,
                dense_score=dense.get(row),
                lexical_score=lexical.get(row),
                fused_score=fused[row],
                dense_rank=dense_positions.get(row),
                lexical_rank=lexical_positions.get(row),
                generation_id=index.manifest.generation_id,
                byte_start=0,
                byte_end=len(chunk_bytes),
                content_sha256=chunk.content_sha256,
            )
            results.append(result)
            traces.append(
                RetrievalTraceHitV2(
                    workspace_id=result.workspace_id,
                    generation_id=result.generation_id,
                    source_id=result.source_id,
                    chunk_id=result.chunk_id,
                    content_utf8=result.text,
                    content_sha256=result.content_sha256,
                    dense_score=result.dense_score,
                    lexical_score=result.lexical_score,
                    fused_score=result.fused_score,
                    dense_rank=result.dense_rank,
                    lexical_rank=result.lexical_rank,
                    fused_rank=fused_rank,
                )
            )
        return tuple(results), tuple(traces)
