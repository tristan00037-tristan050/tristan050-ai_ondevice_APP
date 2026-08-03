"""Independent, deterministic Helper1 retrieval evaluation contracts.

The evaluator consumes ranking records rather than importing the production
retriever.  Protected corpus bytes and answer keys are supplied by a separate
approved loader; this module never opens a repository fixture as a substitute.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .contracts import (
    canonical_json,
    require_digest,
    require_finite,
    require_int,
    require_safe_id,
    require_uuid,
    sha256_bytes,
)


class RetrievalEvaluationError(RuntimeError):
    pass


SPLITS = frozenset({"training", "calibration", "sealed_test"})
EVALUATOR_SPEC = {
    "schema_version": "butler.helper1.retrieval-evaluator.v1",
    "ranking_order": ["score_desc", "source_id_asc", "chunk_id_asc"],
    "metrics": [
        "recall_at_k",
        "mrr_at_k",
        "ndcg_at_k",
        "precision_at_k",
        "abstention_precision",
        "abstention_recall",
        "wrong_workspace_leakage",
        "stale_generation_rate",
        "evidence_span_validity",
    ],
    "gain": "binary",
    "floating_point": "python-float64-finite",
}


@dataclass(frozen=True, slots=True)
class RelevantEvidence:
    chunk_id: str
    source_id: str
    byte_start: int
    byte_end: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_safe_id(self.chunk_id, "EVALUATION_CHUNK_ID_INVALID")
        require_safe_id(self.source_id, "EVALUATION_SOURCE_ID_INVALID")
        require_int(self.byte_start, minimum=0, maximum=2**31 - 1, code="EVALUATION_SPAN_INVALID")
        require_int(self.byte_end, minimum=1, maximum=2**31 - 1, code="EVALUATION_SPAN_INVALID")
        if self.byte_end <= self.byte_start:
            raise RetrievalEvaluationError("EVALUATION_SPAN_INVALID")
        require_digest(self.evidence_sha256, "EVALUATION_EVIDENCE_DIGEST_INVALID")


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    query_id: str
    group_id: str
    split: str
    workspace_id: str
    generation_id: str
    answerable: bool
    relevant: tuple[RelevantEvidence, ...]
    language: str
    document_type: str
    difficulty: str

    def __post_init__(self) -> None:
        require_safe_id(self.query_id, "EVALUATION_QUERY_ID_INVALID")
        require_safe_id(self.group_id, "EVALUATION_GROUP_ID_INVALID")
        if self.split not in SPLITS:
            raise RetrievalEvaluationError("EVALUATION_SPLIT_INVALID")
        require_uuid(self.workspace_id, "EVALUATION_WORKSPACE_INVALID")
        require_uuid(self.generation_id, "EVALUATION_GENERATION_INVALID")
        if type(self.answerable) is not bool:
            raise RetrievalEvaluationError("EVALUATION_ANSWERABILITY_INVALID")
        if self.answerable != bool(self.relevant):
            raise RetrievalEvaluationError("EVALUATION_RELEVANCE_INVALID")
        if len({item.chunk_id for item in self.relevant}) != len(self.relevant):
            raise RetrievalEvaluationError("EVALUATION_RELEVANCE_DUPLICATE")
        for value in (self.language, self.document_type, self.difficulty):
            require_safe_id(value, "EVALUATION_STRATUM_INVALID")


@dataclass(frozen=True, slots=True)
class EvaluationHit:
    workspace_id: str
    generation_id: str
    chunk_id: str
    source_id: str
    score: float
    content_utf8: bytes

    def __post_init__(self) -> None:
        require_uuid(self.workspace_id, "EVALUATION_HIT_WORKSPACE_INVALID")
        require_uuid(self.generation_id, "EVALUATION_HIT_GENERATION_INVALID")
        require_safe_id(self.chunk_id, "EVALUATION_HIT_CHUNK_INVALID")
        require_safe_id(self.source_id, "EVALUATION_HIT_SOURCE_INVALID")
        require_finite(self.score, "EVALUATION_HIT_SCORE_INVALID")
        if not isinstance(self.content_utf8, bytes) or not self.content_utf8:
            raise RetrievalEvaluationError("EVALUATION_HIT_CONTENT_INVALID")
        try:
            self.content_utf8.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RetrievalEvaluationError("EVALUATION_HIT_UNICODE_INVALID") from exc


def evaluator_sha256() -> str:
    return sha256_bytes(canonical_json(EVALUATOR_SPEC))


def validate_group_splits(records: Iterable[EvaluationQuery]) -> None:
    observed: dict[str, str] = {}
    query_ids: set[str] = set()
    for record in records:
        if record.query_id in query_ids:
            raise RetrievalEvaluationError("EVALUATION_QUERY_DUPLICATE")
        query_ids.add(record.query_id)
        previous = observed.setdefault(record.group_id, record.split)
        if previous != record.split:
            raise RetrievalEvaluationError("BLOCK_EVALUATION_GROUP_LEAKAGE")


def _validate_ranking(hits: Sequence[EvaluationHit]) -> None:
    if len({hit.chunk_id for hit in hits}) != len(hits):
        raise RetrievalEvaluationError("EVALUATION_RANKING_DUPLICATE")
    expected = sorted(hits, key=lambda hit: (-hit.score, hit.source_id, hit.chunk_id))
    if list(hits) != expected:
        raise RetrievalEvaluationError("EVALUATION_RANKING_NONDETERMINISTIC")


def _span_valid(hit: EvaluationHit, evidence: RelevantEvidence) -> bool:
    if evidence.byte_end > len(hit.content_utf8):
        return False
    selected = hit.content_utf8[evidence.byte_start : evidence.byte_end]
    try:
        selected.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return sha256_bytes(selected) == evidence.evidence_sha256


def evaluate_rankings(
    records: Sequence[EvaluationQuery],
    rankings: Mapping[str, Sequence[EvaluationHit]],
    *,
    split: str,
    k: int,
    corpus_sha256: str,
    policy_sha256: str,
    approved_threshold_policy_sha256: str | None,
    approved_calibration_receipt_sha256: str | None = None,
) -> dict[str, object]:
    """Evaluate one immutable split; never select or tune a policy."""
    if split not in {"calibration", "sealed_test"}:
        raise RetrievalEvaluationError("EVALUATION_SPLIT_INVALID")
    require_int(k, minimum=1, maximum=1000, code="EVALUATION_K_INVALID")
    require_digest(corpus_sha256, "EVALUATION_CORPUS_DIGEST_INVALID")
    require_digest(policy_sha256, "EVALUATION_POLICY_DIGEST_INVALID")
    if approved_threshold_policy_sha256 is not None:
        require_digest(
            approved_threshold_policy_sha256,
            "EVALUATION_THRESHOLD_POLICY_INVALID",
        )
    if approved_calibration_receipt_sha256 is not None:
        require_digest(
            approved_calibration_receipt_sha256,
            "EVALUATION_APPROVAL_RECEIPT_INVALID",
        )
    validate_group_splits(records)
    selected = tuple(record for record in records if record.split == split)
    if not selected or set(rankings) != {record.query_id for record in selected}:
        raise RetrievalEvaluationError("EVALUATION_INVENTORY_MISMATCH")

    recall_total = reciprocal_total = ndcg_total = precision_total = 0.0
    wrong_workspace = stale_generation = checked_hits = 0
    span_valid = span_checked = 0
    predicted_abstentions = actual_unanswerable = correct_abstentions = 0
    strata: dict[str, int] = {}
    for record in selected:
        hits = tuple(rankings[record.query_id])[:k]
        _validate_ranking(hits)
        relevant_by_chunk = {item.chunk_id: item for item in record.relevant}
        relevant_positions: list[int] = []
        for position, hit in enumerate(hits, start=1):
            checked_hits += 1
            if hit.workspace_id != record.workspace_id:
                wrong_workspace += 1
            if hit.generation_id != record.generation_id:
                stale_generation += 1
            evidence = relevant_by_chunk.get(hit.chunk_id)
            if evidence is not None and hit.source_id == evidence.source_id:
                relevant_positions.append(position)
                span_checked += 1
                span_valid += int(_span_valid(hit, evidence))
        predicted_abstention = len(hits) == 0
        actual_unanswerable += int(not record.answerable)
        predicted_abstentions += int(predicted_abstention)
        correct_abstentions += int(predicted_abstention and not record.answerable)
        relevant_count = len(record.relevant)
        if relevant_count:
            found = len(set(relevant_positions))
            recall_total += found / relevant_count
            precision_total += found / k
            reciprocal_total += 0.0 if not relevant_positions else 1.0 / min(relevant_positions)
            dcg = sum(1.0 / math.log2(position + 1) for position in relevant_positions)
            ideal = sum(
                1.0 / math.log2(position + 1)
                for position in range(1, min(relevant_count, k) + 1)
            )
            ndcg_total += 0.0 if ideal == 0.0 else dcg / ideal
        stratum = f"{record.language}:{record.document_type}:{record.difficulty}"
        strata[stratum] = strata.get(stratum, 0) + 1

    count = len(selected)
    metrics = {
        "recall_at_k": recall_total / count,
        "mrr_at_k": reciprocal_total / count,
        "ndcg_at_k": ndcg_total / count,
        "precision_at_k": precision_total / count,
        "abstention_precision": (
            correct_abstentions / predicted_abstentions if predicted_abstentions else 0.0
        ),
        "abstention_recall": (
            correct_abstentions / actual_unanswerable if actual_unanswerable else 0.0
        ),
        "wrong_workspace_leakage": wrong_workspace / max(1, checked_hits),
        "stale_generation_rate": stale_generation / max(1, checked_hits),
        "evidence_span_validity": span_valid / max(1, span_checked),
    }
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in metrics.values()):
        raise RetrievalEvaluationError("EVALUATION_METRIC_INVALID")
    gate = (
        "BLOCK_RETRIEVAL_POLICY_UNCALIBRATED"
        if (
            approved_threshold_policy_sha256 is None
            or approved_calibration_receipt_sha256 is None
        )
        else "READY_FOR_PROTECTED_THRESHOLD_CHECK"
    )
    return {
        "schema_version": "butler.helper1.retrieval-evaluation-report.v1",
        "corpus_sha256": corpus_sha256,
        "policy_sha256": policy_sha256,
        "evaluator_sha256": evaluator_sha256(),
        "split": split,
        "sample_count": count,
        "k": k,
        "metrics": metrics,
        "strata_sample_counts": dict(sorted(strata.items())),
        "approved_threshold_policy_sha256": approved_threshold_policy_sha256,
        "approved_calibration_receipt_sha256": approved_calibration_receipt_sha256,
        "gate": gate,
    }
