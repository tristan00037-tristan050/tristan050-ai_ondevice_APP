"""Independent, deterministic Helper1 retrieval evaluation contracts.

The evaluator consumes ranking records rather than importing the production
retriever.  Protected corpus bytes and answer keys are supplied by a separate
approved loader; this module never opens a repository fixture as a substitute.
"""
from __future__ import annotations

import hmac
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping, Sequence

from .contracts import (
    AnswerCaseRecordV2,
    AnswerClaimV2,
    EvaluationAnswerDecision,
    EvaluationRunSubjectV2,
    EvaluationVariant,
    RetrievalCaseRecordV2,
    RetrievalDecision,
    canonical_json,
    require_digest,
    require_finite,
    require_int,
    require_safe_id,
    require_uuid,
    sha256_bytes,
)
from .failure_codes import Helper1FailureCode, Helper1V61Error


class RetrievalEvaluationError(RuntimeError):
    pass


SPLITS = frozenset({"training", "calibration", "sealed_test"})
TRACKS = frozenset(
    {"private_retrieval", "source_generalization", "unanswerable", "canary_ablation"}
)
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


@dataclass(frozen=True, slots=True)
class RelevantEvidenceV2:
    source_id: str
    chunk_id: str
    evidence_sha256: str
    grade: int = 1

    def __post_init__(self) -> None:
        require_safe_id(self.source_id, "EVALUATION_SOURCE_ID_INVALID")
        require_safe_id(self.chunk_id, "EVALUATION_CHUNK_ID_INVALID")
        require_digest(self.evidence_sha256, "EVALUATION_EVIDENCE_DIGEST_INVALID")
        require_int(self.grade, minimum=1, maximum=3, code="EVALUATION_GRADE_INVALID")


@dataclass(frozen=True, slots=True)
class AllowedEvidenceV2:
    source_id: str
    chunk_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_safe_id(self.source_id, "EVALUATION_SOURCE_ID_INVALID")
        require_safe_id(self.chunk_id, "EVALUATION_CHUNK_ID_INVALID")
        require_digest(self.evidence_sha256, "EVALUATION_EVIDENCE_DIGEST_INVALID")

    @property
    def key(self) -> tuple[str, str, str]:
        return self.source_id, self.chunk_id, self.evidence_sha256

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class ClaimEvidenceBindingV2:
    fact_sha256: str
    allowed_evidence: tuple[AllowedEvidenceV2, ...]

    def __post_init__(self) -> None:
        require_digest(self.fact_sha256, "EVALUATION_FACT_DIGEST_INVALID")
        if not self.allowed_evidence:
            raise RetrievalEvaluationError("EVALUATION_CLAIM_EVIDENCE_BINDING_INVALID")
        keys = tuple(item.key for item in self.allowed_evidence)
        if len(keys) != len(set(keys)):
            raise RetrievalEvaluationError("EVALUATION_CLAIM_EVIDENCE_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "fact_sha256": self.fact_sha256,
            "allowed_evidence": [item.to_dict() for item in self.allowed_evidence],
        }


@dataclass(frozen=True, slots=True)
class EvaluationQueryV2:
    query_id: str
    group_id: str
    paraphrase_cluster_id: str
    source_family_id: str
    split: str
    track: str
    query_utf8: str
    query_sha256: str
    workspace_id: str
    generation_id: str
    answerable: bool
    language: str
    document_type: str
    difficulty: str
    robustness_tags: tuple[str, ...]
    relevant: tuple[RelevantEvidenceV2, ...]
    required_claim_evidence_bindings: tuple[ClaimEvidenceBindingV2, ...] = ()
    forbidden_fact_sha256: tuple[str, ...] = ()
    canary_value_sha256: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.query_id,
            self.group_id,
            self.paraphrase_cluster_id,
            self.source_family_id,
            self.language,
            self.document_type,
            self.difficulty,
        ):
            require_safe_id(value, "EVALUATION_QUERY_FIELD_INVALID")
        if self.split not in SPLITS or self.track not in TRACKS:
            raise RetrievalEvaluationError("EVALUATION_PARTITION_INVALID")
        if not isinstance(self.query_utf8, str) or not self.query_utf8.strip():
            raise RetrievalEvaluationError("EVALUATION_QUERY_TEXT_INVALID")
        require_digest(self.query_sha256, "EVALUATION_QUERY_DIGEST_INVALID")
        if self.query_sha256 != sha256_bytes(self.query_utf8.encode("utf-8")):
            raise RetrievalEvaluationError("EVALUATION_QUERY_DIGEST_MISMATCH")
        require_uuid(self.workspace_id, "EVALUATION_WORKSPACE_INVALID")
        require_uuid(self.generation_id, "EVALUATION_GENERATION_INVALID")
        if type(self.answerable) is not bool or self.answerable != bool(self.relevant):
            raise RetrievalEvaluationError("EVALUATION_RELEVANCE_INVALID")
        if self.track == "unanswerable" and self.answerable:
            raise RetrievalEvaluationError("EVALUATION_TRACK_INVALID")
        if self.track == "canary_ablation" and self.canary_value_sha256 is None:
            raise RetrievalEvaluationError("EVALUATION_CANARY_INVALID")
        if self.canary_value_sha256 is not None:
            require_digest(self.canary_value_sha256, "EVALUATION_CANARY_INVALID")
        if len(set(self.robustness_tags)) != len(self.robustness_tags):
            raise RetrievalEvaluationError("EVALUATION_ROBUSTNESS_DUPLICATE")
        for tag in self.robustness_tags:
            require_safe_id(tag, "EVALUATION_ROBUSTNESS_INVALID")
        fact_digests = tuple(
            binding.fact_sha256 for binding in self.required_claim_evidence_bindings
        )
        if self.answerable != bool(fact_digests) or len(fact_digests) != len(set(fact_digests)):
            raise RetrievalEvaluationError("EVALUATION_CLAIM_EVIDENCE_BINDING_INVALID")
        relevant_keys = {
            (item.source_id, item.chunk_id, item.evidence_sha256) for item in self.relevant
        }
        if any(
            item.key not in relevant_keys
            for binding in self.required_claim_evidence_bindings
            for item in binding.allowed_evidence
        ):
            raise RetrievalEvaluationError("EVALUATION_CLAIM_EVIDENCE_BINDING_INVALID")
        for digest in (*fact_digests, *self.forbidden_fact_sha256):
            require_digest(digest, "EVALUATION_FACT_DIGEST_INVALID")
        if set(fact_digests) & set(self.forbidden_fact_sha256):
            raise RetrievalEvaluationError("EVALUATION_FACT_CONFLICT")

    def to_dict(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "group_id": self.group_id,
            "paraphrase_cluster_id": self.paraphrase_cluster_id,
            "source_family_id": self.source_family_id,
            "split": self.split,
            "track": self.track,
            "query_utf8": self.query_utf8,
            "query_sha256": self.query_sha256,
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "answerable": self.answerable,
            "language": self.language,
            "document_type": self.document_type,
            "difficulty": self.difficulty,
            "robustness_tags": list(self.robustness_tags),
            "relevant": [
                {
                    "source_id": item.source_id,
                    "chunk_id": item.chunk_id,
                    "evidence_sha256": item.evidence_sha256,
                    "grade": item.grade,
                }
                for item in self.relevant
            ],
            "required_claim_evidence_bindings": [
                binding.to_dict() for binding in self.required_claim_evidence_bindings
            ],
            "forbidden_fact_sha256": list(self.forbidden_fact_sha256),
            "canary_value_sha256": self.canary_value_sha256,
        }


def evaluation_query_v2_from_mapping(value: Mapping[str, object]) -> EvaluationQueryV2:
    expected = {
        "query_id",
        "group_id",
        "paraphrase_cluster_id",
        "source_family_id",
        "split",
        "track",
        "query_utf8",
        "query_sha256",
        "workspace_id",
        "generation_id",
        "answerable",
        "language",
        "document_type",
        "difficulty",
        "robustness_tags",
        "relevant",
        "required_claim_evidence_bindings",
        "forbidden_fact_sha256",
        "canary_value_sha256",
    }
    if (
        set(value) != expected
        or not isinstance(value.get("relevant"), list)
        or not isinstance(value.get("required_claim_evidence_bindings"), list)
    ):
        raise RetrievalEvaluationError("EVALUATION_QUERY_SCHEMA_INVALID")
    relevant_items = value["relevant"]
    relevant = tuple(
        RelevantEvidenceV2(**item)
        for item in relevant_items
        if isinstance(item, dict)
    )
    if len(relevant) != len(relevant_items):
        raise RetrievalEvaluationError("EVALUATION_QUERY_SCHEMA_INVALID")
    bindings: list[ClaimEvidenceBindingV2] = []
    for item in value["required_claim_evidence_bindings"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"fact_sha256", "allowed_evidence"}
            or not isinstance(item.get("allowed_evidence"), list)
        ):
            raise RetrievalEvaluationError("EVALUATION_QUERY_SCHEMA_INVALID")
        allowed: list[AllowedEvidenceV2] = []
        for evidence in item["allowed_evidence"]:
            if (
                not isinstance(evidence, dict)
                or set(evidence) != {"source_id", "chunk_id", "evidence_sha256"}
            ):
                raise RetrievalEvaluationError("EVALUATION_QUERY_SCHEMA_INVALID")
            allowed.append(AllowedEvidenceV2(**evidence))
        bindings.append(
            ClaimEvidenceBindingV2(
                fact_sha256=item["fact_sha256"],
                allowed_evidence=tuple(allowed),
            )
        )
    return EvaluationQueryV2(
        query_id=value["query_id"],
        group_id=value["group_id"],
        paraphrase_cluster_id=value["paraphrase_cluster_id"],
        source_family_id=value["source_family_id"],
        split=value["split"],
        track=value["track"],
        query_utf8=value["query_utf8"],
        query_sha256=value["query_sha256"],
        workspace_id=value["workspace_id"],
        generation_id=value["generation_id"],
        answerable=value["answerable"],
        language=value["language"],
        document_type=value["document_type"],
        difficulty=value["difficulty"],
        robustness_tags=tuple(value["robustness_tags"]),
        relevant=relevant,
        required_claim_evidence_bindings=tuple(bindings),
        forbidden_fact_sha256=tuple(value["forbidden_fact_sha256"]),
        canary_value_sha256=value["canary_value_sha256"],
    )  # type: ignore[arg-type]


def ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise Helper1V61Error(Helper1FailureCode.METRIC_DENOMINATOR_ZERO)
    if numerator < 0 or numerator > denominator:
        raise Helper1V61Error(Helper1FailureCode.METRIC_COUNT_INVALID)
    return (numerator * 1_000_000 + denominator // 2) // denominator


def _fraction_ppm(value: Fraction) -> int:
    return ppm(value.numerator, value.denominator)


def validate_partition_v2(
    records: Sequence[EvaluationQueryV2],
    *,
    sealed_manifest_sha256: str,
    tuning_history_manifest_sha256: Sequence[str],
) -> None:
    require_digest(sealed_manifest_sha256, "EVALUATION_MANIFEST_DIGEST_INVALID")
    if sealed_manifest_sha256 in tuning_history_manifest_sha256:
        raise Helper1V61Error(Helper1FailureCode.SEALED_TEST_REUSED_AFTER_TUNING)
    query_digests: set[str] = set()
    groups: dict[str, str] = {}
    paraphrases: dict[str, str] = {}
    source_families: dict[str, str] = {}
    for record in records:
        if record.query_sha256 in query_digests:
            raise RetrievalEvaluationError("EVALUATION_QUERY_DUPLICATE")
        query_digests.add(record.query_sha256)
        for identity, observed, code in (
            (record.group_id, groups, Helper1FailureCode.EVALUATION_GROUP_LEAKAGE),
            (
                record.paraphrase_cluster_id,
                paraphrases,
                Helper1FailureCode.EVALUATION_GROUP_LEAKAGE,
            ),
            (
                record.source_family_id,
                source_families,
                Helper1FailureCode.EVALUATION_SOURCE_FAMILY_LEAKAGE,
            ),
        ):
            previous = observed.setdefault(identity, record.split)
            if previous != record.split:
                raise Helper1V61Error(code)


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))


def evaluation_query_manifest_sha256(queries: Sequence[EvaluationQueryV2]) -> str:
    ordered = sorted((record.to_dict() for record in queries), key=lambda row: str(row["query_id"]))
    if len({str(row["query_id"]) for row in ordered}) != len(ordered):
        raise RetrievalEvaluationError("EVALUATION_QUERY_DUPLICATE")
    return sha256_bytes(canonical_json(ordered))


def _validate_record_identity(
    retrieval: RetrievalCaseRecordV2,
    answer: AnswerCaseRecordV2,
    subject: EvaluationRunSubjectV2,
    *,
    variant: EvaluationVariant,
) -> None:
    expected_subject = subject.digest
    expected_index = (
        subject.normal_index_manifest_sha256
        if variant is EvaluationVariant.NORMAL
        else subject.ablation_index_manifest_sha256
    )
    if expected_index is None:
        raise RetrievalEvaluationError("EVALUATION_ABLATION_SUBJECT_MISSING")
    if (
        retrieval.run_id != subject.run_id
        or answer.run_id != subject.run_id
        or retrieval.evaluation_run_subject_sha256 != expected_subject
        or answer.evaluation_run_subject_sha256 != expected_subject
        or answer.execution_variant is not variant
        or retrieval.policy_sha256 != subject.retrieval_policy_sha256
        or retrieval.encoder_space_sha256 != subject.encoder_space_sha256
        or retrieval.index_manifest_sha256 != expected_index
        or answer.normal_index_manifest_sha256 != subject.normal_index_manifest_sha256
        or answer.generator_identity_sha256 != subject.generator_identity_sha256
        or answer.prompt_template_sha256 != subject.prompt_template_sha256
        or answer.decoding_policy_sha256 != subject.decoding_policy_sha256
        or answer.seed != subject.seed
    ):
        raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")
    if variant is EvaluationVariant.NORMAL:
        if answer.ablation_index_manifest_sha256 is not None:
            raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")
    elif answer.ablation_index_manifest_sha256 != subject.ablation_index_manifest_sha256:
        raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")


def _citation_verdict(
    answer: AnswerCaseRecordV2,
    retrieval: RetrievalCaseRecordV2,
    query: EvaluationQueryV2,
    claim: AnswerClaimV2,
) -> tuple[bool, bool]:
    """Return (citation-bytes-valid, claim-faithful-to-sealed-answer-key).

    Citation byte validity and faithfulness are deliberately separate.  A
    well-formed citation to unrelated text must not raise the grounding score.
    The sealed manifest is the authority for the exact supported fact digests;
    retrieved bytes must also be one of that query's gold evidence objects.
    """
    hits = {(hit.source_id, hit.chunk_id): hit for hit in retrieval.hits}
    allowed_by_fact = {
        binding.fact_sha256: {item.key for item in binding.allowed_evidence}
        for binding in query.required_claim_evidence_bindings
    }
    citation_valid = False
    faithful = False
    for citation in answer.citations:
        if citation.claim_id != claim.claim_id:
            continue
        hit = hits.get((citation.source_id, citation.chunk_id))
        if hit is None:
            raise RetrievalEvaluationError("EVALUATION_CITATION_NOT_RETRIEVED")
        raw = hit.content_utf8.encode("utf-8")
        if citation.evidence_byte_end > len(raw):
            raise RetrievalEvaluationError("EVALUATION_CITATION_SPAN_INVALID")
        selected = raw[citation.evidence_byte_start : citation.evidence_byte_end]
        try:
            selected.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RetrievalEvaluationError("EVALUATION_CITATION_SPAN_INVALID") from exc
        if not hmac.compare_digest(sha256_bytes(selected), citation.evidence_sha256):
            raise RetrievalEvaluationError("EVALUATION_CITATION_DIGEST_MISMATCH")
        citation_valid = True
        faithful = faithful or (
            (hit.source_id, hit.chunk_id, hit.content_sha256)
            in allowed_by_fact.get(claim.text_sha256, set())
        )
    return citation_valid, faithful


def evaluate_quality_v2(
    queries: Sequence[EvaluationQueryV2],
    retrieval_records: Mapping[str, RetrievalCaseRecordV2],
    answer_records: Mapping[str, AnswerCaseRecordV2],
    *,
    execution_subject: EvaluationRunSubjectV2,
    ablation_retrieval_records: Mapping[str, RetrievalCaseRecordV2] | None = None,
    ablation_answer_records: Mapping[str, AnswerCaseRecordV2] | None = None,
    split: str,
    corpus_manifest_sha256: str,
    retrieval_policy_sha256: str,
    threshold_policy_sha256: str,
    ks: tuple[int, ...] = (1, 5, 10),
) -> dict[str, object]:
    """Recompute quality only from immutable per-case records."""
    if split not in {"calibration", "sealed_test"}:
        raise RetrievalEvaluationError("EVALUATION_SPLIT_INVALID")
    require_digest(corpus_manifest_sha256, "EVALUATION_CORPUS_DIGEST_INVALID")
    require_digest(retrieval_policy_sha256, "EVALUATION_POLICY_DIGEST_INVALID")
    require_digest(threshold_policy_sha256, "EVALUATION_THRESHOLD_POLICY_INVALID")
    selected = tuple(record for record in queries if record.split == split)
    expected = {record.query_id for record in selected}
    if not selected or set(retrieval_records) != expected or set(answer_records) != expected:
        raise RetrievalEvaluationError("EVALUATION_INVENTORY_MISMATCH")
    if not ks or tuple(sorted(set(ks))) != ks:
        raise RetrievalEvaluationError("EVALUATION_K_INVALID")
    if (
        evaluation_query_manifest_sha256(queries) != execution_subject.query_manifest_sha256
        or corpus_manifest_sha256 != execution_subject.corpus_manifest_sha256
        or retrieval_policy_sha256 != execution_subject.retrieval_policy_sha256
        or threshold_policy_sha256 != execution_subject.threshold_policy_sha256
    ):
        raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")
    canary_ids = {record.query_id for record in selected if record.track == "canary_ablation"}
    if canary_ids:
        if (
            execution_subject.ablation_index_manifest_sha256 is None
            or ablation_retrieval_records is None
            or ablation_answer_records is None
            or set(ablation_retrieval_records) != canary_ids
            or set(ablation_answer_records) != canary_ids
        ):
            raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
    elif ablation_retrieval_records or ablation_answer_records:
        raise RetrievalEvaluationError("EVALUATION_ABLATION_INVENTORY_INVALID")

    answerable_count = sum(record.answerable for record in selected)
    if answerable_count == 0:
        raise Helper1V61Error(Helper1FailureCode.METRIC_DENOMINATOR_ZERO)
    recall: dict[int, Fraction] = {k: Fraction(0, 1) for k in ks}
    success: dict[int, int] = {k: 0 for k in ks}
    precision: dict[int, Fraction] = {k: Fraction(0, 1) for k in ks}
    reciprocal = Fraction(0, 1)
    ndcg_total = 0.0
    tp = fp = fn = tn = 0
    supported_claims = all_claims = 0
    citation_valid_claims = 0
    canary_leakage_count = 0
    wrong_workspace = stale_generation = 0
    strata: dict[str, int] = {}

    for query in selected:
        retrieval = retrieval_records[query.query_id]
        answer = answer_records[query.query_id]
        if retrieval.query_id != query.query_id or answer.query_id != query.query_id:
            raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")
        _validate_record_identity(
            retrieval,
            answer,
            execution_subject,
            variant=EvaluationVariant.NORMAL,
        )
        hits = retrieval.hits if retrieval.decision is RetrievalDecision.RETRIEVE else ()
        wrong_workspace += sum(hit.workspace_id != query.workspace_id for hit in hits)
        stale_generation += sum(hit.generation_id != query.generation_id for hit in hits)
        if wrong_workspace:
            raise Helper1V61Error(Helper1FailureCode.WRONG_WORKSPACE_LEAKAGE)
        if stale_generation:
            raise Helper1V61Error(Helper1FailureCode.STALE_GENERATION_LEAKAGE)

        if query.answerable:
            relevant = {
                (item.source_id, item.chunk_id, item.evidence_sha256): item.grade
                for item in query.relevant
            }
            ranks = [
                (position, relevant[(hit.source_id, hit.chunk_id, hit.content_sha256)])
                for position, hit in enumerate(hits, 1)
                if (hit.source_id, hit.chunk_id, hit.content_sha256) in relevant
            ]
            for k in ks:
                found = len({position for position, _grade in ranks if position <= k})
                recall[k] += Fraction(found, len(relevant))
                success[k] += int(found > 0)
                precision[k] += Fraction(found, k)
            if ranks and ranks[0][0] <= 10:
                reciprocal += Fraction(1, ranks[0][0])
            observed_grades = [
                relevant.get((hit.source_id, hit.chunk_id, hit.content_sha256), 0)
                for hit in hits[:10]
            ]
            ideal_grades = sorted(relevant.values(), reverse=True)[:10]
            ideal = _dcg(ideal_grades)
            ndcg_total += 0.0 if ideal == 0.0 else _dcg(observed_grades) / ideal

        predicted_abstain = answer.decision is EvaluationAnswerDecision.ABSTAIN
        if not query.answerable and predicted_abstain:
            tp += 1
        elif query.answerable and predicted_abstain:
            fp += 1
        elif not query.answerable:
            fn += 1
        else:
            tn += 1
        if answer.decision is EvaluationAnswerDecision.ANSWER:
            all_claims += len(answer.claims)
            for claim in answer.claims:
                citation_valid, faithful = _citation_verdict(
                    answer,
                    retrieval,
                    query,
                    claim,
                )
                citation_valid_claims += int(citation_valid)
                supported_claims += int(faithful)
        if query.track == "canary_ablation":
            assert ablation_retrieval_records is not None
            assert ablation_answer_records is not None
            ablation_retrieval = ablation_retrieval_records[query.query_id]
            ablation_answer = ablation_answer_records[query.query_id]
            if (
                ablation_retrieval.query_id != query.query_id
                or ablation_answer.query_id != query.query_id
            ):
                raise RetrievalEvaluationError("EVALUATION_SUBJECT_MISMATCH")
            _validate_record_identity(
                ablation_retrieval,
                ablation_answer,
                execution_subject,
                variant=EvaluationVariant.ABLATION,
            )
            if (
                answer.decision is not EvaluationAnswerDecision.ANSWER
                or query.canary_value_sha256 not in {claim.text_sha256 for claim in answer.claims}
            ):
                raise Helper1V61Error(Helper1FailureCode.RETRIEVAL_DEPENDENCE_NOT_PROVEN)
            canary_leakage_count += int(
                ablation_answer.decision is not EvaluationAnswerDecision.ABSTAIN
            )
        stratum = f"{query.language}:{query.document_type}:{query.difficulty}"
        strata[stratum] = strata.get(stratum, 0) + 1

    def ratio_or_undefined(numerator: int, denominator: int) -> dict[str, object]:
        if denominator == 0:
            return {"status": "UNDEFINED", "reason_code": "METRIC_DENOMINATOR_ZERO", "ppm": None}
        return {"status": "DEFINED", "reason_code": None, "ppm": ppm(numerator, denominator)}

    metrics: dict[str, object] = {}
    for k in ks:
        metrics[f"recall_at_{k}_ppm"] = _fraction_ppm(recall[k] / answerable_count)
        metrics[f"success_at_{k}_ppm"] = ppm(success[k], answerable_count)
        metrics[f"precision_at_{k}_ppm"] = _fraction_ppm(precision[k] / answerable_count)
    metrics["mrr_at_10_ppm"] = _fraction_ppm(reciprocal / answerable_count)
    metrics["ndcg_at_10_ppm"] = int(math.floor((ndcg_total / answerable_count) * 1_000_000 + 0.5))
    metrics["abstention_precision"] = ratio_or_undefined(tp, tp + fp)
    metrics["abstention_recall"] = ratio_or_undefined(tp, tp + fn)
    precision_status = metrics["abstention_precision"]
    recall_status = metrics["abstention_recall"]
    if precision_status["ppm"] is None or recall_status["ppm"] is None:
        metrics["abstention_f1"] = {
            "status": "UNDEFINED",
            "reason_code": "METRIC_DENOMINATOR_ZERO",
            "ppm": None,
        }
    else:
        p_value = int(precision_status["ppm"])
        r_value = int(recall_status["ppm"])
        metrics["abstention_f1"] = ratio_or_undefined(2 * p_value * r_value, 1_000_000 * (p_value + r_value))
    metrics["false_abstention_rate"] = ratio_or_undefined(fp, fp + tn)
    metrics["claim_grounding_precision"] = ratio_or_undefined(supported_claims, all_claims)
    metrics["retrieval_recall_ppm"] = metrics["recall_at_10_ppm"]
    metrics["abstention_precision_ppm"] = metrics["abstention_precision"]["ppm"]
    metrics["abstention_recall_ppm"] = metrics["abstention_recall"]["ppm"]
    metrics["evidence_span_validity_ppm"] = (
        0 if all_claims == 0 else ppm(citation_valid_claims, all_claims)
    )
    metrics["wrong_workspace_rate_ppm"] = 0 if wrong_workspace == 0 else 1_000_000
    metrics["stale_generation_rate_ppm"] = 0 if stale_generation == 0 else 1_000_000

    report = {
        "schema_version": "butler.helper1.retrieval-quality-report.v2",
        "split": split,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "evaluation_run_subject_sha256": execution_subject.digest,
        "threshold_approval_receipt_sha256": execution_subject.threshold_approval_receipt_sha256,
        "threshold_policy_sha256": threshold_policy_sha256,
        "threshold_state": "APPROVED",
        "sample_count": len(selected),
        "answerable_count": answerable_count,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": metrics,
        "canary_leakage_count": canary_leakage_count,
        "wrong_workspace_hit_count": wrong_workspace,
        "stale_generation_hit_count": stale_generation,
        "strata_sample_counts": dict(sorted(strata.items())),
    }
    return {**report, "report_sha256": sha256_bytes(canonical_json(report))}


def verify_declared_report_v2(
    declared: Mapping[str, object], recomputed: Mapping[str, object]
) -> None:
    if not isinstance(declared, Mapping) or canonical_json(dict(declared)) != canonical_json(dict(recomputed)):
        raise Helper1V61Error(Helper1FailureCode.MEASUREMENT_RECOMPUTE_MISMATCH)
