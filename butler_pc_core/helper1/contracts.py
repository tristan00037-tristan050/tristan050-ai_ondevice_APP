"""Strict Helper1 v2 contracts shared by indexing, retrieval and release."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import struct
import threading
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")
MOVING_REVISIONS = frozenset({"", "main", "master", "HEAD", "latest"})


class Helper1ContractError(ValueError):
    """Stable contract failure; the message is a public reason code only."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hmac_sha256(key: bytes, *parts: bytes) -> str:
    digest = hmac.new(key, digestmod=hashlib.sha256)
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def require_digest(value: object, code: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise Helper1ContractError(code)
    return value


def require_uuid(value: object, code: str) -> str:
    if not isinstance(value, str):
        raise Helper1ContractError(code)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise Helper1ContractError(code) from exc
    if str(parsed) != value.lower() or parsed.version not in {1, 2, 3, 4, 5}:
        raise Helper1ContractError(code)
    return value


def require_safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or SAFE_ID_RE.fullmatch(value) is None:
        raise Helper1ContractError(code)
    return value


def require_int(value: object, *, minimum: int, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Helper1ContractError(code)
    if value < minimum or value > maximum:
        raise Helper1ContractError(code)
    return value


def require_finite(value: object, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Helper1ContractError(code)
    number = float(value)
    if not math.isfinite(number):
        raise Helper1ContractError(code)
    return number


class AnswerKind(str, Enum):
    ANSWERED = "ANSWERED"
    REFUSED_NO_GROUNDING = "REFUSED_NO_GROUNDING"
    REFUSED_ASSET_MISSING = "REFUSED_ASSET_MISSING"
    REFUSED_POLICY = "REFUSED_POLICY"
    REFUSED_DLP = "REFUSED_DLP"
    REFUSED_INJECTION = "REFUSED_INJECTION"
    REFUSED_INDEX_INVALID = "REFUSED_INDEX_INVALID"
    REFUSED_MEASUREMENT_INVALID = "REFUSED_MEASUREMENT_INVALID"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class RetrievalDecision(str, Enum):
    RETRIEVE = "RETRIEVE"
    ABSTAIN = "ABSTAIN"


class EvaluationAnswerDecision(str, Enum):
    ANSWER = "ANSWER"
    ABSTAIN = "ABSTAIN"


class EvaluationVariant(str, Enum):
    NORMAL = "NORMAL"
    ABLATION = "ABLATION"


HTTP_STATUS_BY_KIND: Mapping[AnswerKind, int] = {
    AnswerKind.ANSWERED: 200,
    AnswerKind.REFUSED_NO_GROUNDING: 200,
    AnswerKind.REFUSED_ASSET_MISSING: 503,
    AnswerKind.REFUSED_POLICY: 403,
    AnswerKind.REFUSED_DLP: 451,
    AnswerKind.REFUSED_INJECTION: 422,
    AnswerKind.REFUSED_INDEX_INVALID: 409,
    AnswerKind.REFUSED_MEASUREMENT_INVALID: 503,
    AnswerKind.CANCELLED: 409,
    AnswerKind.FAILED: 500,
}


@dataclass(frozen=True)
class AssetIdentity:
    role: str
    model_id: str
    upstream_revision: str
    closure_manifest_sha256: str
    runtime_name: str
    runtime_version: str
    runtime_binary_sha256: str
    tokenizer_sha256: str

    def __post_init__(self) -> None:
        if self.role not in {"helper1_embed", "helper1_answer"}:
            raise Helper1ContractError("ASSET_ROLE_INVALID")
        require_safe_id(self.role, "ASSET_ROLE_INVALID")
        if (
            not isinstance(self.model_id, str)
            or not self.model_id
            or len(self.model_id) > 128
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", self.model_id) is None
        ):
            raise Helper1ContractError("ASSET_MODEL_ID_INVALID")
        if (
            not isinstance(self.upstream_revision, str)
            or self.upstream_revision in MOVING_REVISIONS
            or len(self.upstream_revision) > 128
        ):
            raise Helper1ContractError("ASSET_REVISION_NOT_PINNED")
        require_digest(self.closure_manifest_sha256, "ASSET_CLOSURE_DIGEST_INVALID")
        require_safe_id(self.runtime_name, "ASSET_RUNTIME_NAME_INVALID")
        require_safe_id(self.runtime_version, "ASSET_RUNTIME_VERSION_INVALID")
        require_digest(self.runtime_binary_sha256, "ASSET_RUNTIME_DIGEST_INVALID")
        require_digest(self.tokenizer_sha256, "ASSET_TOKENIZER_DIGEST_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EncoderIdentity:
    asset: AssetIdentity
    pooling: str
    normalize: bool
    dimension: int
    max_length: int
    truncation_policy: str
    document_prefix_sha256: str
    query_prefix_sha256: str
    output_dtype: str = "float32"

    def __post_init__(self) -> None:
        if self.asset.role != "helper1_embed":
            raise Helper1ContractError("ENCODER_ASSET_ROLE_INVALID")
        if self.pooling not in {"cls", "mean", "last_token"}:
            raise Helper1ContractError("ENCODER_POOLING_INVALID")
        if not isinstance(self.normalize, bool):
            raise Helper1ContractError("ENCODER_NORMALIZE_INVALID")
        require_int(
            self.dimension,
            minimum=1,
            maximum=65536,
            code="ENCODER_DIMENSION_INVALID",
        )
        require_int(
            self.max_length,
            minimum=1,
            maximum=1048576,
            code="ENCODER_MAX_LENGTH_INVALID",
        )
        if self.truncation_policy not in {"reject", "head", "tail", "balanced"}:
            raise Helper1ContractError("ENCODER_TRUNCATION_INVALID")
        require_digest(self.document_prefix_sha256, "ENCODER_DOCUMENT_PREFIX_INVALID")
        require_digest(self.query_prefix_sha256, "ENCODER_QUERY_PREFIX_INVALID")
        if self.output_dtype != "float32":
            raise Helper1ContractError("ENCODER_DTYPE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.to_dict(),
            "pooling": self.pooling,
            "normalize": self.normalize,
            "dimension": self.dimension,
            "max_length": self.max_length,
            "truncation_policy": self.truncation_policy,
            "document_prefix_sha256": self.document_prefix_sha256,
            "query_prefix_sha256": self.query_prefix_sha256,
            "output_dtype": self.output_dtype,
        }

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


class EmbeddingSpaceMismatch(RuntimeError):
    pass


def assert_same_space(index_encoder: EncoderIdentity, query_encoder: EncoderIdentity) -> None:
    if not hmac.compare_digest(index_encoder.digest, query_encoder.digest):
        raise EmbeddingSpaceMismatch("EMBEDDING_SPACE_MISMATCH")


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, str)
            or not self.path
            or len(self.path) > 512
            or self.path.startswith("/")
            or "\\" in self.path
            or "\x00" in self.path
            or ".." in self.path.split("/")
            or "." in self.path.split("/")
        ):
            raise Helper1ContractError("INDEX_ARTIFACT_PATH_INVALID")
        require_int(
            self.bytes,
            minimum=1,
            maximum=2**63 - 1,
            code="INDEX_ARTIFACT_SIZE_INVALID",
        )
        require_digest(self.sha256, "INDEX_ARTIFACT_DIGEST_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexManifest:
    workspace_id: str
    generation_id: str
    encoder: EncoderIdentity
    lexical_tokenizer_sha256: str
    chunker_policy_sha256: str
    parser_isolation_policy_sha256: str
    document_set_hmac_sha256: str
    policy_sha256: str
    chunk_count: int
    embedding_rows: int
    embedding_dimension: int
    lexical_term_count: int
    artifacts: Mapping[str, ArtifactRecord]
    previous_generation_id: str | None = None
    schema_version: str = "butler.helper1.index.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.index.v2":
            raise Helper1ContractError("INDEX_SCHEMA_INVALID")
        require_uuid(self.workspace_id, "WORKSPACE_ID_INVALID")
        require_uuid(self.generation_id, "GENERATION_ID_INVALID")
        if self.previous_generation_id is not None:
            require_uuid(self.previous_generation_id, "PREVIOUS_GENERATION_ID_INVALID")
        require_digest(self.lexical_tokenizer_sha256, "LEXICAL_TOKENIZER_INVALID")
        require_digest(self.chunker_policy_sha256, "CHUNKER_POLICY_INVALID")
        require_digest(
            self.parser_isolation_policy_sha256,
            "PARSER_ISOLATION_POLICY_INVALID",
        )
        require_digest(self.document_set_hmac_sha256, "DOCUMENT_SET_HMAC_INVALID")
        require_digest(self.policy_sha256, "INDEX_POLICY_DIGEST_INVALID")
        require_int(self.chunk_count, minimum=1, maximum=2**31 - 1, code="CHUNK_COUNT_INVALID")
        require_int(
            self.embedding_rows,
            minimum=1,
            maximum=2**31 - 1,
            code="EMBEDDING_ROWS_INVALID",
        )
        require_int(
            self.embedding_dimension,
            minimum=1,
            maximum=65536,
            code="EMBEDDING_DIMENSION_INVALID",
        )
        require_int(
            self.lexical_term_count,
            minimum=1,
            maximum=2**31 - 1,
            code="LEXICAL_TERM_COUNT_INVALID",
        )
        if self.chunk_count != self.embedding_rows:
            raise Helper1ContractError("INDEX_COUNT_MISMATCH")
        if self.embedding_dimension != self.encoder.dimension:
            raise Helper1ContractError("INDEX_DIMENSION_MISMATCH")
        if set(self.artifacts) != {"chunks", "embeddings", "lexical_index"}:
            raise Helper1ContractError("INDEX_ARTIFACT_SET_INVALID")
        if len({record.path for record in self.artifacts.values()}) != 3:
            raise Helper1ContractError("INDEX_ARTIFACT_PATH_DUPLICATE")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "previous_generation_id": self.previous_generation_id,
            "encoder": self.encoder.to_dict(),
            "lexical_tokenizer_sha256": self.lexical_tokenizer_sha256,
            "chunker_policy_sha256": self.chunker_policy_sha256,
            "parser_isolation_policy_sha256": self.parser_isolation_policy_sha256,
            "document_set_hmac_sha256": self.document_set_hmac_sha256,
            "policy_sha256": self.policy_sha256,
            "chunk_count": self.chunk_count,
            "embedding_rows": self.embedding_rows,
            "embedding_dimension": self.embedding_dimension,
            "lexical_term_count": self.lexical_term_count,
            "artifacts": {
                key: record.to_dict() for key, record in sorted(self.artifacts.items())
            },
        }

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


@dataclass(frozen=True)
class RetrievedChunk:
    workspace_id: str
    chunk_id: str
    source_id: str
    text: str
    dense_score: float | None
    lexical_score: float | None
    fused_score: float
    dense_rank: int | None
    lexical_rank: int | None
    generation_id: str
    byte_start: int
    byte_end: int
    content_sha256: str

    def __post_init__(self) -> None:
        require_uuid(self.workspace_id, "CHUNK_WORKSPACE_INVALID")
        require_safe_id(self.chunk_id, "CHUNK_ID_INVALID")
        require_safe_id(self.source_id, "SOURCE_ID_INVALID")
        require_uuid(self.generation_id, "CHUNK_GENERATION_INVALID")
        if not isinstance(self.text, str) or not self.text:
            raise Helper1ContractError("CHUNK_TEXT_INVALID")
        if self.dense_score is None and self.lexical_score is None:
            raise Helper1ContractError("CHUNK_SCORE_ABSENT")
        for score in (self.dense_score, self.lexical_score, self.fused_score):
            if score is not None:
                require_finite(score, "CHUNK_SCORE_INVALID")
        for rank in (self.dense_rank, self.lexical_rank):
            if rank is not None:
                require_int(rank, minimum=1, maximum=1000, code="CHUNK_RANK_INVALID")
        require_int(self.byte_start, minimum=0, maximum=2**31 - 1, code="CHUNK_BYTE_RANGE_INVALID")
        require_int(self.byte_end, minimum=1, maximum=2**31 - 1, code="CHUNK_BYTE_RANGE_INVALID")
        if self.byte_start != 0 or self.byte_end != len(self.text.encode("utf-8")):
            raise Helper1ContractError("CHUNK_BYTE_RANGE_INVALID")
        require_digest(self.content_sha256, "CHUNK_CONTENT_DIGEST_INVALID")
        if not hmac.compare_digest(
            self.content_sha256, sha256_bytes(self.text.encode("utf-8"))
        ):
            raise Helper1ContractError("CHUNK_CONTENT_DIGEST_MISMATCH")


@dataclass(frozen=True)
class GroundingPolicy:
    min_chunks: int
    min_fused_score: float
    min_grounding_ratio: float
    require_citation: bool = True
    max_answer_chars: int = 65536

    def __post_init__(self) -> None:
        require_int(self.min_chunks, minimum=1, maximum=100, code="MIN_CHUNKS_INVALID")
        require_finite(self.min_fused_score, "MIN_FUSED_SCORE_INVALID")
        ratio = require_finite(self.min_grounding_ratio, "MIN_GROUNDING_RATIO_INVALID")
        if ratio <= 0.0 or ratio > 1.0:
            raise Helper1ContractError("MIN_GROUNDING_RATIO_INVALID")
        if self.require_citation is not True:
            raise Helper1ContractError("CITATION_CANNOT_BE_DISABLED")
        require_int(
            self.max_answer_chars,
            minimum=1,
            maximum=65536,
            code="MAX_ANSWER_CHARS_INVALID",
        )


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    chunk_id: str
    evidence_start: int
    evidence_end: int

    def __post_init__(self) -> None:
        require_safe_id(self.claim_id, "CLAIM_ID_INVALID")
        require_safe_id(self.chunk_id, "CLAIM_CHUNK_ID_INVALID")
        if not isinstance(self.text, str) or not self.text:
            raise Helper1ContractError("CLAIM_TEXT_INVALID")
        require_int(
            self.evidence_start,
            minimum=0,
            maximum=2**31 - 1,
            code="EVIDENCE_RANGE_INVALID",
        )
        require_int(
            self.evidence_end,
            minimum=1,
            maximum=2**31 - 1,
            code="EVIDENCE_RANGE_INVALID",
        )
        if self.evidence_end <= self.evidence_start:
            raise Helper1ContractError("EVIDENCE_RANGE_INVALID")


@dataclass(frozen=True)
class Citation:
    claim_id: str
    workspace_id: str
    generation_id: str
    chunk_id: str
    source_id: str
    evidence_start: int
    evidence_end: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_safe_id(self.claim_id, "CITATION_CLAIM_ID_INVALID")
        require_uuid(self.workspace_id, "CITATION_WORKSPACE_INVALID")
        require_uuid(self.generation_id, "CITATION_GENERATION_INVALID")
        require_safe_id(self.chunk_id, "CITATION_CHUNK_ID_INVALID")
        require_safe_id(self.source_id, "CITATION_SOURCE_ID_INVALID")
        require_int(
            self.evidence_start,
            minimum=0,
            maximum=2**31 - 1,
            code="CITATION_RANGE_INVALID",
        )
        require_int(
            self.evidence_end,
            minimum=1,
            maximum=2**31 - 1,
            code="CITATION_RANGE_INVALID",
        )
        if self.evidence_end <= self.evidence_start:
            raise Helper1ContractError("CITATION_RANGE_INVALID")
        require_digest(self.evidence_sha256, "CITATION_DIGEST_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnswerResult:
    kind: AnswerKind
    request_id: str
    workspace_id: str
    generation_id: str | None
    answer: str | None
    reason_code: str | None
    model_identity_sha256: str | None
    index_manifest_sha256: str | None
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    release_receipt_sha256: str | None = None
    execution_receipt: Mapping[str, Any] | None = None
    schema_version: str = "butler.helper1.answer.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.answer.v2":
            raise Helper1ContractError("ANSWER_SCHEMA_INVALID")
        if not isinstance(self.kind, AnswerKind):
            raise Helper1ContractError("ANSWER_KIND_INVALID")
        require_uuid(self.request_id, "REQUEST_ID_INVALID")
        require_uuid(self.workspace_id, "WORKSPACE_ID_INVALID")
        if self.generation_id is not None:
            require_uuid(self.generation_id, "GENERATION_ID_INVALID")
        if self.kind is AnswerKind.ANSWERED:
            if (
                not isinstance(self.answer, str)
                or not self.answer
                or len(self.answer) > 65536
            ):
                raise Helper1ContractError("ANSWERED_WITHOUT_VALID_ANSWER")
            if self.reason_code is not None:
                raise Helper1ContractError("ANSWERED_WITH_REASON")
            if self.generation_id is None:
                raise Helper1ContractError("ANSWERED_WITHOUT_GENERATION")
            require_digest(
                self.model_identity_sha256, "ANSWERED_WITHOUT_MODEL_IDENTITY"
            )
            require_digest(
                self.index_manifest_sha256, "ANSWERED_WITHOUT_INDEX_IDENTITY"
            )
            require_digest(
                self.release_receipt_sha256, "ANSWERED_WITHOUT_RELEASE_RECEIPT"
            )
            if not self.citations:
                raise Helper1ContractError("ANSWERED_WITHOUT_CITATION")
            if any(
                citation.workspace_id != self.workspace_id
                or citation.generation_id != self.generation_id
                for citation in self.citations
            ):
                raise Helper1ContractError("CITATION_SUBJECT_BINDING_INVALID")
        else:
            if self.answer is not None or self.citations:
                raise Helper1ContractError("NONANSWER_WITH_PAYLOAD")
            if (
                not isinstance(self.reason_code, str)
                or REASON_RE.fullmatch(self.reason_code) is None
            ):
                raise Helper1ContractError("NONANSWER_REASON_INVALID")
            if self.release_receipt_sha256 is not None:
                raise Helper1ContractError("NONANSWER_WITH_RELEASE_RECEIPT")
            if self.execution_receipt is not None:
                raise Helper1ContractError("NONANSWER_WITH_EXECUTION_RECEIPT")

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_BY_KIND[self.kind]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "answer": self.answer,
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "reason_code": self.reason_code,
            "model_identity_sha256": self.model_identity_sha256,
            "index_manifest_sha256": self.index_manifest_sha256,
            "citations": [citation.to_dict() for citation in self.citations],
            "release_receipt_sha256": self.release_receipt_sha256,
            "execution_receipt": (
                dict(self.execution_receipt) if self.execution_receipt is not None else None
            ),
        }


def float64_bits(value: float, code: str) -> str:
    """Return an exact binary64 representation and reject ambiguous -0.0."""
    number = require_finite(value, code)
    if number == 0.0 and math.copysign(1.0, number) < 0.0:
        raise Helper1ContractError(code)
    return struct.pack(">d", number).hex()


@dataclass(frozen=True, slots=True)
class EvaluationRunSubjectV2:
    """One immutable identity for a complete protected quality run."""

    run_id: str
    run_attempt: int
    source_commit: str
    source_tree: str
    query_manifest_sha256: str
    corpus_manifest_sha256: str
    retrieval_policy_sha256: str
    threshold_policy_sha256: str
    threshold_approval_receipt_sha256: str
    encoder_space_sha256: str
    normal_index_manifest_sha256: str
    ablation_index_manifest_sha256: str | None
    generator_identity_sha256: str
    prompt_template_sha256: str
    decoding_policy_sha256: str
    seed: int
    schema_version: str = "butler.helper1.evaluation-run-subject.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.evaluation-run-subject.v2":
            raise Helper1ContractError("EVALUATION_SUBJECT_SCHEMA_INVALID")
        require_safe_id(self.run_id, "EVALUATION_SUBJECT_RUN_INVALID")
        require_int(
            self.run_attempt,
            minimum=1,
            maximum=1_000_000,
            code="EVALUATION_SUBJECT_RUN_INVALID",
        )
        for value in (self.source_commit, self.source_tree):
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
                raise Helper1ContractError("EVALUATION_SUBJECT_SOURCE_INVALID")
        for value in (
            self.query_manifest_sha256,
            self.corpus_manifest_sha256,
            self.retrieval_policy_sha256,
            self.threshold_policy_sha256,
            self.threshold_approval_receipt_sha256,
            self.encoder_space_sha256,
            self.normal_index_manifest_sha256,
            self.generator_identity_sha256,
            self.prompt_template_sha256,
            self.decoding_policy_sha256,
        ):
            require_digest(value, "EVALUATION_SUBJECT_IDENTITY_INVALID")
        if self.ablation_index_manifest_sha256 is not None:
            require_digest(
                self.ablation_index_manifest_sha256,
                "EVALUATION_SUBJECT_IDENTITY_INVALID",
            )
            if hmac.compare_digest(
                self.ablation_index_manifest_sha256,
                self.normal_index_manifest_sha256,
            ):
                raise Helper1ContractError("EVALUATION_SUBJECT_ABLATION_INVALID")
        require_int(
            self.seed,
            minimum=0,
            maximum=2**63 - 1,
            code="EVALUATION_SUBJECT_SEED_INVALID",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "query_manifest_sha256": self.query_manifest_sha256,
            "corpus_manifest_sha256": self.corpus_manifest_sha256,
            "retrieval_policy_sha256": self.retrieval_policy_sha256,
            "threshold_policy_sha256": self.threshold_policy_sha256,
            "threshold_approval_receipt_sha256": self.threshold_approval_receipt_sha256,
            "encoder_space_sha256": self.encoder_space_sha256,
            "normal_index_manifest_sha256": self.normal_index_manifest_sha256,
            "ablation_index_manifest_sha256": self.ablation_index_manifest_sha256,
            "generator_identity_sha256": self.generator_identity_sha256,
            "prompt_template_sha256": self.prompt_template_sha256,
            "decoding_policy_sha256": self.decoding_policy_sha256,
            "seed": self.seed,
        }

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


def evaluation_run_subject_v2_from_mapping(
    value: Mapping[str, object],
) -> EvaluationRunSubjectV2:
    expected = {
        "schema_version",
        "run_id",
        "run_attempt",
        "source_commit",
        "source_tree",
        "query_manifest_sha256",
        "corpus_manifest_sha256",
        "retrieval_policy_sha256",
        "threshold_policy_sha256",
        "threshold_approval_receipt_sha256",
        "encoder_space_sha256",
        "normal_index_manifest_sha256",
        "ablation_index_manifest_sha256",
        "generator_identity_sha256",
        "prompt_template_sha256",
        "decoding_policy_sha256",
        "seed",
    }
    if type(value) is not dict or set(value) != expected:
        raise Helper1ContractError("EVALUATION_SUBJECT_SCHEMA_INVALID")
    try:
        return EvaluationRunSubjectV2(**value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise Helper1ContractError("EVALUATION_SUBJECT_SCHEMA_INVALID") from exc


@dataclass(frozen=True, slots=True)
class RetrievalTraceHitV2:
    workspace_id: str
    generation_id: str
    source_id: str
    chunk_id: str
    content_utf8: str
    content_sha256: str
    dense_score: float | None
    lexical_score: float | None
    fused_score: float
    dense_rank: int | None
    lexical_rank: int | None
    fused_rank: int

    def __post_init__(self) -> None:
        require_uuid(self.workspace_id, "RETRIEVAL_HIT_WORKSPACE_INVALID")
        require_uuid(self.generation_id, "RETRIEVAL_HIT_GENERATION_INVALID")
        require_safe_id(self.source_id, "RETRIEVAL_HIT_SOURCE_INVALID")
        require_safe_id(self.chunk_id, "RETRIEVAL_HIT_CHUNK_INVALID")
        if not isinstance(self.content_utf8, str) or not self.content_utf8:
            raise Helper1ContractError("RETRIEVAL_HIT_CONTENT_INVALID")
        require_digest(self.content_sha256, "RETRIEVAL_HIT_CONTENT_DIGEST_INVALID")
        if not hmac.compare_digest(
            self.content_sha256,
            sha256_bytes(self.content_utf8.encode("utf-8")),
        ):
            raise Helper1ContractError("RETRIEVAL_HIT_CONTENT_DIGEST_MISMATCH")
        if self.dense_score is None and self.lexical_score is None:
            raise Helper1ContractError("RETRIEVAL_HIT_SCORE_ABSENT")
        if self.dense_score is not None:
            float64_bits(self.dense_score, "RETRIEVAL_HIT_DENSE_SCORE_INVALID")
        if self.lexical_score is not None:
            float64_bits(self.lexical_score, "RETRIEVAL_HIT_LEXICAL_SCORE_INVALID")
        float64_bits(self.fused_score, "RETRIEVAL_HIT_FUSED_SCORE_INVALID")
        for rank in (self.dense_rank, self.lexical_rank):
            if rank is not None:
                require_int(rank, minimum=1, maximum=1_000_000, code="RETRIEVAL_HIT_RANK_INVALID")
        require_int(
            self.fused_rank,
            minimum=1,
            maximum=1_000_000,
            code="RETRIEVAL_HIT_RANK_INVALID",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "content_utf8": self.content_utf8,
            "content_sha256": self.content_sha256,
            "dense_score_bits": (
                None
                if self.dense_score is None
                else float64_bits(self.dense_score, "RETRIEVAL_HIT_DENSE_SCORE_INVALID")
            ),
            "lexical_score_bits": (
                None
                if self.lexical_score is None
                else float64_bits(self.lexical_score, "RETRIEVAL_HIT_LEXICAL_SCORE_INVALID")
            ),
            "fused_score_bits": float64_bits(
                self.fused_score, "RETRIEVAL_HIT_FUSED_SCORE_INVALID"
            ),
            "dense_rank": self.dense_rank,
            "lexical_rank": self.lexical_rank,
            "fused_rank": self.fused_rank,
        }


@dataclass(frozen=True, slots=True)
class RetrievalCaseRecordV2:
    query_id: str
    run_id: str
    evaluation_run_subject_sha256: str
    policy_sha256: str
    encoder_space_sha256: str
    index_manifest_sha256: str
    started_monotonic_ns: int
    finished_monotonic_ns: int
    decision: RetrievalDecision
    reason_code: str | None
    hits: tuple[RetrievalTraceHitV2, ...]
    schema_version: str = "butler.helper1.retrieval-case.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.retrieval-case.v2":
            raise Helper1ContractError("RETRIEVAL_CASE_SCHEMA_INVALID")
        require_safe_id(self.query_id, "RETRIEVAL_CASE_QUERY_INVALID")
        require_safe_id(self.run_id, "RETRIEVAL_CASE_RUN_INVALID")
        require_digest(
            self.evaluation_run_subject_sha256,
            "RETRIEVAL_CASE_SUBJECT_INVALID",
        )
        for value in (
            self.policy_sha256,
            self.encoder_space_sha256,
            self.index_manifest_sha256,
        ):
            require_digest(value, "RETRIEVAL_CASE_IDENTITY_INVALID")
        require_int(
            self.started_monotonic_ns,
            minimum=0,
            maximum=2**63 - 1,
            code="RETRIEVAL_CASE_TIME_INVALID",
        )
        require_int(
            self.finished_monotonic_ns,
            minimum=1,
            maximum=2**63 - 1,
            code="RETRIEVAL_CASE_TIME_INVALID",
        )
        if self.finished_monotonic_ns < self.started_monotonic_ns:
            raise Helper1ContractError("RETRIEVAL_CASE_TIME_INVALID")
        if not isinstance(self.decision, RetrievalDecision):
            raise Helper1ContractError("RETRIEVAL_CASE_DECISION_INVALID")
        if self.decision is RetrievalDecision.RETRIEVE:
            if not self.hits or self.reason_code is not None:
                raise Helper1ContractError("RETRIEVAL_CASE_DECISION_INVALID")
        elif self.hits or REASON_RE.fullmatch(self.reason_code or "") is None:
            raise Helper1ContractError("RETRIEVAL_CASE_DECISION_INVALID")
        if len({(hit.source_id, hit.chunk_id) for hit in self.hits}) != len(self.hits):
            raise Helper1ContractError("RETRIEVAL_CASE_HIT_DUPLICATE")
        expected = sorted(
            self.hits,
            key=lambda hit: (hit.fused_rank, hit.source_id, hit.chunk_id),
        )
        if list(self.hits) != expected or [hit.fused_rank for hit in self.hits] != list(
            range(1, len(self.hits) + 1)
        ):
            raise Helper1ContractError("RANKING_NONDETERMINISTIC")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query_id": self.query_id,
            "run_id": self.run_id,
            "evaluation_run_subject_sha256": self.evaluation_run_subject_sha256,
            "policy_sha256": self.policy_sha256,
            "encoder_space_sha256": self.encoder_space_sha256,
            "index_manifest_sha256": self.index_manifest_sha256,
            "started_monotonic_ns": self.started_monotonic_ns,
            "finished_monotonic_ns": self.finished_monotonic_ns,
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "hits": [hit.to_dict() for hit in self.hits],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        return {**payload, "record_sha256": sha256_bytes(canonical_json(payload))}


@dataclass(frozen=True, slots=True)
class AnswerClaimV2:
    claim_id: str
    text_sha256: str
    answer_byte_start: int
    answer_byte_end: int

    def __post_init__(self) -> None:
        require_safe_id(self.claim_id, "ANSWER_CLAIM_ID_INVALID")
        require_digest(self.text_sha256, "ANSWER_CLAIM_DIGEST_INVALID")
        require_int(self.answer_byte_start, minimum=0, maximum=2**31 - 1, code="ANSWER_CLAIM_SPAN_INVALID")
        require_int(self.answer_byte_end, minimum=1, maximum=2**31 - 1, code="ANSWER_CLAIM_SPAN_INVALID")
        if self.answer_byte_end <= self.answer_byte_start:
            raise Helper1ContractError("ANSWER_CLAIM_SPAN_INVALID")


@dataclass(frozen=True, slots=True)
class AnswerCitationV2:
    claim_id: str
    source_id: str
    chunk_id: str
    evidence_byte_start: int
    evidence_byte_end: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_safe_id(self.claim_id, "ANSWER_CITATION_CLAIM_INVALID")
        require_safe_id(self.source_id, "ANSWER_CITATION_SOURCE_INVALID")
        require_safe_id(self.chunk_id, "ANSWER_CITATION_CHUNK_INVALID")
        require_int(self.evidence_byte_start, minimum=0, maximum=2**31 - 1, code="ANSWER_CITATION_SPAN_INVALID")
        require_int(self.evidence_byte_end, minimum=1, maximum=2**31 - 1, code="ANSWER_CITATION_SPAN_INVALID")
        if self.evidence_byte_end <= self.evidence_byte_start:
            raise Helper1ContractError("ANSWER_CITATION_SPAN_INVALID")
        require_digest(self.evidence_sha256, "ANSWER_CITATION_DIGEST_INVALID")


@dataclass(frozen=True, slots=True)
class AnswerCaseRecordV2:
    query_id: str
    run_id: str
    evaluation_run_subject_sha256: str
    execution_variant: EvaluationVariant
    generator_identity_sha256: str
    prompt_template_sha256: str
    decision: EvaluationAnswerDecision
    reason_code: str | None
    answer_utf8: str | None
    claims: tuple[AnswerClaimV2, ...]
    citations: tuple[AnswerCitationV2, ...]
    normal_index_manifest_sha256: str
    ablation_index_manifest_sha256: str | None
    seed: int
    decoding_policy_sha256: str
    started_monotonic_ns: int
    finished_monotonic_ns: int
    schema_version: str = "butler.helper1.answer-case.v2"

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.answer-case.v2":
            raise Helper1ContractError("ANSWER_CASE_SCHEMA_INVALID")
        require_safe_id(self.query_id, "ANSWER_CASE_QUERY_INVALID")
        require_safe_id(self.run_id, "ANSWER_CASE_RUN_INVALID")
        require_digest(
            self.evaluation_run_subject_sha256,
            "ANSWER_CASE_SUBJECT_INVALID",
        )
        if not isinstance(self.execution_variant, EvaluationVariant):
            raise Helper1ContractError("ANSWER_CASE_VARIANT_INVALID")
        for value in (
            self.generator_identity_sha256,
            self.prompt_template_sha256,
            self.normal_index_manifest_sha256,
            self.decoding_policy_sha256,
        ):
            require_digest(value, "ANSWER_CASE_IDENTITY_INVALID")
        if self.ablation_index_manifest_sha256 is not None:
            require_digest(self.ablation_index_manifest_sha256, "ANSWER_CASE_IDENTITY_INVALID")
        if self.execution_variant is EvaluationVariant.NORMAL:
            if self.ablation_index_manifest_sha256 is not None:
                raise Helper1ContractError("ANSWER_CASE_VARIANT_INVALID")
        elif self.ablation_index_manifest_sha256 is None:
            raise Helper1ContractError("ANSWER_CASE_VARIANT_INVALID")
        require_int(self.seed, minimum=0, maximum=2**63 - 1, code="ANSWER_CASE_SEED_INVALID")
        require_int(self.started_monotonic_ns, minimum=0, maximum=2**63 - 1, code="ANSWER_CASE_TIME_INVALID")
        require_int(self.finished_monotonic_ns, minimum=1, maximum=2**63 - 1, code="ANSWER_CASE_TIME_INVALID")
        if self.finished_monotonic_ns < self.started_monotonic_ns:
            raise Helper1ContractError("ANSWER_CASE_TIME_INVALID")
        if not isinstance(self.decision, EvaluationAnswerDecision):
            raise Helper1ContractError("ANSWER_CASE_DECISION_INVALID")
        if self.decision is EvaluationAnswerDecision.ANSWER:
            if not self.answer_utf8 or self.reason_code is not None or not self.claims or not self.citations:
                raise Helper1ContractError("ANSWER_CASE_DECISION_INVALID")
            answer_bytes = self.answer_utf8.encode("utf-8")
            for claim in self.claims:
                if claim.answer_byte_end > len(answer_bytes):
                    raise Helper1ContractError("ANSWER_CLAIM_SPAN_INVALID")
                selected = answer_bytes[claim.answer_byte_start : claim.answer_byte_end]
                try:
                    selected.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise Helper1ContractError("ANSWER_CLAIM_SPAN_INVALID") from exc
                if not hmac.compare_digest(sha256_bytes(selected), claim.text_sha256):
                    raise Helper1ContractError("ANSWER_CLAIM_DIGEST_MISMATCH")
            claim_ids = {claim.claim_id for claim in self.claims}
            if len(claim_ids) != len(self.claims) or any(
                citation.claim_id not in claim_ids for citation in self.citations
            ):
                raise Helper1ContractError("ANSWER_CITATION_BINDING_INVALID")
        elif (
            self.answer_utf8 is not None
            or self.claims
            or self.citations
            or REASON_RE.fullmatch(self.reason_code or "") is None
        ):
            raise Helper1ContractError("ANSWER_CASE_DECISION_INVALID")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query_id": self.query_id,
            "run_id": self.run_id,
            "evaluation_run_subject_sha256": self.evaluation_run_subject_sha256,
            "execution_variant": self.execution_variant.value,
            "generator_identity_sha256": self.generator_identity_sha256,
            "prompt_template_sha256": self.prompt_template_sha256,
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "answer_utf8": self.answer_utf8,
            "answer_sha256": (
                None if self.answer_utf8 is None else sha256_bytes(self.answer_utf8.encode("utf-8"))
            ),
            "claims": [asdict(claim) for claim in self.claims],
            "citations": [asdict(citation) for citation in self.citations],
            "normal_index_manifest_sha256": self.normal_index_manifest_sha256,
            "ablation_index_manifest_sha256": self.ablation_index_manifest_sha256,
            "seed": self.seed,
            "decoding_policy_sha256": self.decoding_policy_sha256,
            "started_monotonic_ns": self.started_monotonic_ns,
            "finished_monotonic_ns": self.finished_monotonic_ns,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        return {**payload, "record_sha256": sha256_bytes(canonical_json(payload))}


@dataclass
class TerminalLatch:
    """Per-request one-shot terminal transition."""

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _terminal: str | None = field(default=None, init=False)

    def commit(self, terminal: str) -> None:
        with self._lock:
            if self._terminal is not None:
                raise Helper1ContractError("TERMINAL_ALREADY_COMMITTED")
            self._terminal = terminal

    @property
    def count(self) -> int:
        with self._lock:
            return int(self._terminal is not None)


def validate_no_unknown_keys(
    value: Mapping[str, Any], allowed: Sequence[str], code: str
) -> None:
    if set(value) - set(allowed):
        raise Helper1ContractError(code)
