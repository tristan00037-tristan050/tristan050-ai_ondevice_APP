from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from butler_pc_core.learning_adapters.folder_doc import ALLOWED_EXTENSIONS
from butler_pc_core.learning_core.runner import LearningIntakeRunner

from .producer_common import (
    DEFAULT_VERIFIED_AT,
    DIGEST_ONLY_EVIDENCE_REF,
    ProducerInputError,
    artifact_to_mapping,
    bool_field,
    build_candidate_envelope,
    digest_safe_drop_summary,
    ensure_exact_fields,
    ensure_no_forbidden_keys,
    ingest_candidate,
    int_field,
    normalize_source_refs,
    optional_str_field,
    source_refs_from_mapping,
    str_field,
    validate_digest_or_drop,
)

PRODUCER_VERSION = "folder_doc_producer.v1.0.0"
TARGET_KIND = "folder_doc"
LEARNING_SOURCE_TYPE = "verified_folder_doc"
PAYLOAD_KEYS = frozenset(
    {
        "folder_ingest_approved",
        "traversal_pruned",
        "max_depth",
        "max_files",
        "extension",
        "chunk_digest",
        "previous_manifest_digest",
    }
)


class FolderDocProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class FolderDocLearningArtifact:
    folder_ingest_approved: bool
    traversal_pruned: bool
    max_depth: int
    max_files: int
    extension: str
    chunk_digest: str
    expected_effect_digest: str
    previous_manifest_digest: str | None = None
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def _fail(code: str) -> None:
    raise FolderDocProducerError(code)


def _normalize_extension(value: str) -> str:
    extension = value.strip().lower()
    if not extension.startswith("."):
        extension = "." + extension
    return extension


def coerce_folder_doc_artifact(artifact: FolderDocLearningArtifact | Mapping[str, Any]) -> FolderDocLearningArtifact:
    data = artifact_to_mapping(artifact, FolderDocLearningArtifact)
    ensure_no_forbidden_keys(data)
    ensure_exact_fields(data, FolderDocLearningArtifact)
    previous_manifest_digest = optional_str_field(
        data,
        "previous_manifest_digest",
        "PREVIOUS_MANIFEST_DIGEST_INVALID",
    )
    return FolderDocLearningArtifact(
        folder_ingest_approved=bool_field(
            data,
            "folder_ingest_approved",
            default=False,
            error_code="FOLDER_INGEST_APPROVED_INVALID",
        ),
        traversal_pruned=bool_field(
            data,
            "traversal_pruned",
            default=False,
            error_code="TRAVERSAL_PRUNED_INVALID",
        ),
        max_depth=int_field(data, "max_depth", "MAX_DEPTH_INVALID"),
        max_files=int_field(data, "max_files", "MAX_FILES_INVALID"),
        extension=_normalize_extension(str_field(data, "extension", "EXTENSION_REQUIRED")),
        chunk_digest=str_field(data, "chunk_digest", "CHUNK_DIGEST_REQUIRED"),
        expected_effect_digest=str_field(data, "expected_effect_digest", "EXPECTED_EFFECT_DIGEST_REQUIRED"),
        previous_manifest_digest=previous_manifest_digest,
        source_refs=source_refs_from_mapping(data),
        verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
        verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
        evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
        evidence_ref=str(data.get("evidence_ref", DIGEST_ONLY_EVIDENCE_REF)).strip(),
    )


def build_folder_doc_candidate(artifact: FolderDocLearningArtifact | Mapping[str, Any]) -> dict[str, Any]:
    item = coerce_folder_doc_artifact(artifact)
    chunk_digest = validate_digest_or_drop(item.chunk_digest, "CHUNK")
    previous_manifest_digest = validate_digest_or_drop(
        item.previous_manifest_digest,
        "PREVIOUS_MANIFEST",
        required=False,
    )
    evidence_digest = validate_digest_or_drop(item.evidence_digest or chunk_digest, "EVIDENCE")
    source_refs = normalize_source_refs(
        item.source_refs,
        fallback_type="folder",
        fallback_digest=chunk_digest,
    )
    payload = {
        "folder_ingest_approved": item.folder_ingest_approved,
        "traversal_pruned": item.traversal_pruned,
        "max_depth": item.max_depth,
        "max_files": item.max_files,
        "extension": item.extension,
        "chunk_digest": chunk_digest,
        "previous_manifest_digest": previous_manifest_digest,
    }
    if set(payload) != PAYLOAD_KEYS:
        _fail("PAYLOAD_KEYS_INVALID")
    return build_candidate_envelope(
        target_kind=TARGET_KIND,
        adapter_version=PRODUCER_VERSION,
        learning_source_type=LEARNING_SOURCE_TYPE,
        payload=payload,
        expected_effect_digest=item.expected_effect_digest,
        evidence_digest=evidence_digest,
        evidence_ref=item.evidence_ref,
        source_refs=source_refs,
        verified_by=item.verified_by,
        verified_at=item.verified_at,
    )


def ingest_verified_folder_doc(
    artifact: FolderDocLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    try:
        candidate = build_folder_doc_candidate(artifact)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
