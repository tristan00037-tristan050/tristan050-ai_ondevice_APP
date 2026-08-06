from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.approval_closure import (
    EvidenceArtifact,
    REQUIRED_EVIDENCE_ROLES,
    ROLE_MEDIA_TYPES,
    THRESHOLD_POLICY_ROLE,
    evidence_set_sha256,
    recompute_a4_rows,
)
from butler_pc_core.helper1.canonical_json import canonicalize_butler_cj1
from butler_pc_core.helper1.execution import NativeExecutionAuthority
from butler_pc_core.helper1.replay_store import SQLiteReplayStore
from butler_pc_core.helper1.retrieval_policy import (
    EVIDENCE_DOMAIN,
    ProtectedTrustPolicyProvider,
    RetrievalPolicyAuthority,
)

NOW = 1_800_000_000
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
COMMIT = "1" * 40
TREE = "2" * 40
WORKSPACE = "00000000-0000-4000-8000-000000000051"
GENERATION = "00000000-0000-4000-8000-000000000052"
MANIFEST_DIGEST = "3" * 64
EVIDENCE_KEY_ID = "butler/helper1/evidence/v51"
THRESHOLD_KEY_ID = "butler/helper1/threshold/v51"
EVALUATOR_SOURCE = b"deterministic evaluator source v51"
ENCODER_ARTIFACT = b"pinned encoder artifact v51"
CORPUS_MANIFEST = canonicalize_butler_cj1({"documents": ["a", "b"], "version": 51})
INDEX_POLICY = canonicalize_butler_cj1({"hybrid": True, "k": 8})
EVALUATOR_SHA = hashlib.sha256(EVALUATOR_SOURCE).hexdigest()
ENCODER_SHA = hashlib.sha256(ENCODER_ARTIFACT).hexdigest()
CORPUS_SHA = hashlib.sha256(CORPUS_MANIFEST).hexdigest()
INDEX_SHA = hashlib.sha256(INDEX_POLICY).hexdigest()
REQUIRED_STRATA = ["ko:pdf", "ko:txt"]


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def deterministic_keys() -> tuple[Ed25519PrivateKey, Ed25519PrivateKey, Ed25519PrivateKey]:
    return tuple(
        Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32)
        for value in (17, 23, 31)
    )  # type: ignore[return-value]


def policy_bytes(*, epoch: int = 51, enabled: bool = True, repository: str = REPOSITORY) -> tuple[bytes, tuple[Ed25519PrivateKey, ...]]:
    evidence, threshold, activation = deterministic_keys()
    value: dict[str, Any] = {
        "schema_version": "butler.helper1.retrieval-approval-trust-policy.v1",
        "repository": repository,
        "policy_epoch": epoch,
        "enabled": enabled,
        "max_evidence_age_seconds": 3600,
        "keys": [],
    }
    if enabled:
        value.update(
            {
                "max_future_skew_seconds": 30,
                "subject": {"commit_sha": COMMIT, "tree_sha": TREE, "workspace_id": WORKSPACE},
                "required_strata": REQUIRED_STRATA,
                "minimum_sample_count": 4,
                "minimum_per_stratum_count": 2,
                "expected_evaluator_source_sha256": EVALUATOR_SHA,
                "expected_encoder": {
                    "provider": "helper2_sdk",
                    "model": "bge-m3",
                    "revision": "v51",
                    "artifact_sha256": ENCODER_SHA,
                },
                "expected_corpus_manifest_sha256": CORPUS_SHA,
                "expected_index_manifest_policy_sha256": INDEX_SHA,
                "expected_grounding_threshold_ppm": 500_000,
                "expected_abstention_threshold_ppm": 500_000,
                "keys": [
                    {
                        "key_id": EVIDENCE_KEY_ID,
                        "public_key_b64url": b64url(public_bytes(evidence)),
                        "roles": ["EVIDENCE_SIGNER"],
                        "not_before_epoch_s": NOW - 60,
                        "expires_at_epoch_s": NOW + 3600,
                        "revoked": False,
                    },
                    {
                        "key_id": THRESHOLD_KEY_ID,
                        "public_key_b64url": b64url(public_bytes(threshold)),
                        "roles": ["THRESHOLD_POLICY_SIGNER"],
                        "not_before_epoch_s": NOW - 60,
                        "expires_at_epoch_s": NOW + 3600,
                        "revoked": False,
                    },
                ],
            }
        )
    return canonicalize_butler_cj1(value), (evidence, threshold, activation)


def authority(
    tmp_path: Path,
    *,
    epoch: int = 51,
    production: bool = False,
    repository: str = REPOSITORY,
) -> tuple[RetrievalPolicyAuthority, tuple[Ed25519PrivateKey, ...]]:
    raw, keys = policy_bytes(epoch=epoch, repository=repository)
    digest = hashlib.sha256(raw).hexdigest()
    provider = (
        ProtectedTrustPolicyProvider._from_composition_root_bytes(raw, digest)
        if production
        else ProtectedTrustPolicyProvider._for_test(raw, digest)
    )
    result = RetrievalPolicyAuthority.from_composition_root(
        provider,
        SQLiteReplayStore(tmp_path / "replay.sqlite3"),
        lambda: NOW,
    )
    return result, keys


def rows(prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "query_id": f"{prefix}:answerable-hit", "stratum": "ko:txt",
            "answerable": True, "predicted_abstention": False, "relevant_count": 1,
            "retrieved_relevant_count": 1, "first_relevant_rank": 1, "retrieved_count": 1,
            "wrong_workspace_count": 0, "stale_generation_count": 0,
            "span_valid_count": 1, "span_checked_count": 1,
        },
        {
            "query_id": f"{prefix}:answerable-abstain", "stratum": "ko:txt",
            "answerable": True, "predicted_abstention": True, "relevant_count": 1,
            "retrieved_relevant_count": 0, "first_relevant_rank": None, "retrieved_count": 0,
            "wrong_workspace_count": 0, "stale_generation_count": 0,
            "span_valid_count": 0, "span_checked_count": 0,
        },
        {
            "query_id": f"{prefix}:unanswerable-abstain", "stratum": "ko:pdf",
            "answerable": False, "predicted_abstention": True, "relevant_count": 0,
            "retrieved_relevant_count": 0, "first_relevant_rank": None, "retrieved_count": 0,
            "wrong_workspace_count": 0, "stale_generation_count": 0,
            "span_valid_count": 0, "span_checked_count": 0,
        },
        {
            "query_id": f"{prefix}:unanswerable-hit", "stratum": "ko:pdf",
            "answerable": False, "predicted_abstention": False, "relevant_count": 0,
            "retrieved_relevant_count": 0, "first_relevant_rank": None, "retrieved_count": 1,
            "wrong_workspace_count": 0, "stale_generation_count": 0,
            "span_valid_count": 0, "span_checked_count": 0,
        },
    ]


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def threshold_payload() -> dict[str, Any]:
    return {
        "schema_version": "butler.helper1.retrieval-threshold-policy.v1",
        "policy_epoch": 51,
        "evaluator_source_sha256": EVALUATOR_SHA,
        "encoder_provider": "helper2_sdk",
        "encoder_model": "bge-m3",
        "encoder_revision": "v51",
        "encoder_artifact_sha256": ENCODER_SHA,
        "corpus_manifest_sha256": CORPUS_SHA,
        "index_manifest_policy_sha256": INDEX_SHA,
        "grounding_threshold_ppm": 500_000,
        "abstention_threshold_ppm": 500_000,
        "required_strata": REQUIRED_STRATA,
        "minimum_sample_count": 4,
        "minimum_per_stratum_count": 2,
        "minimum_metrics_ppm": {
            "retrieval_recall_ppm": 500_000,
            "abstention_precision_ppm": 500_000,
            "abstention_recall_ppm": 500_000,
            "evidence_span_validity_ppm": 1_000_000,
        },
        "maximum_metrics_ppm": {
            "wrong_workspace_rate_ppm": 0,
            "stale_generation_rate_ppm": 0,
        },
        "issued_at_epoch_s": NOW - 5,
        "expires_at_epoch_s": NOW + 300,
    }


def _split_rows(values: list[dict[str, Any]]) -> tuple[bytes, bytes]:
    labels = [
        {key: row[key] for key in ("query_id", "stratum", "answerable", "relevant_count")}
        for row in values
    ]
    predictions = [
        {
            key: row[key]
            for key in (
                "query_id", "predicted_abstention", "retrieved_relevant_count",
                "first_relevant_rank", "retrieved_count", "wrong_workspace_count",
                "stale_generation_count", "span_valid_count", "span_checked_count",
            )
        }
        for row in values
    ]
    return canonicalize_butler_cj1(labels), canonicalize_butler_cj1(predictions)


def evaluation_material(
    split: str,
    row_values: list[dict[str, Any]],
    threshold_digest: str,
    *,
    calibration_digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    counts, metrics, strata = recompute_a4_rows(row_values)
    labels, predictions = _split_rows(row_values)
    report = canonicalize_butler_cj1(
        {
            "schema_version": "butler.helper1.retrieval-evaluation-report.v1",
            "counts": counts,
            "metrics_ppm": metrics,
            "strata_counts": strata,
        }
    )
    split_inventory = canonicalize_butler_cj1({"split": split, "queries": [row["query_id"] for row in row_values]})
    group_inventory = canonicalize_butler_cj1({"split": split, "groups": [f"{split}-{index}" for index in range(len(row_values))]})
    attachments = {
        EVALUATOR_SHA: EVALUATOR_SOURCE,
        ENCODER_SHA: ENCODER_ARTIFACT,
        CORPUS_SHA: CORPUS_MANIFEST,
        INDEX_SHA: INDEX_POLICY,
        _digest(split_inventory): split_inventory,
        _digest(group_inventory): group_inventory,
        _digest(predictions): predictions,
        _digest(labels): labels,
        _digest(report): report,
    }
    payload: dict[str, Any] = {
        "schema_version": (
            "butler.helper1.retrieval-calibration-receipt.v1"
            if split == "calibration"
            else "butler.helper1.retrieval-sealed-test-receipt.v1"
        ),
        "evaluator_version": "v51",
        "evaluator_source_sha256": EVALUATOR_SHA,
        "encoder_provider": "helper2_sdk",
        "encoder_model": "bge-m3",
        "encoder_revision": "v51",
        "encoder_artifact_sha256": ENCODER_SHA,
        "corpus_manifest_sha256": CORPUS_SHA,
        "split_inventory_sha256": _digest(split_inventory),
        "group_inventory_sha256": _digest(group_inventory),
        "index_manifest_policy_sha256": INDEX_SHA,
        "threshold_policy_sha256": threshold_digest,
        "grounding_threshold_ppm": 500_000,
        "abstention_threshold_ppm": 500_000,
        "sample_count": counts["sample_count"],
        "required_strata": REQUIRED_STRATA,
        "strata_counts": strata,
        "prediction_rows_sha256": _digest(predictions),
        "label_rows_sha256": _digest(labels),
        "evaluation_report_sha256": _digest(report),
        "counts": counts,
        "metrics_ppm": metrics,
        "wrong_workspace_count": counts["wrong_workspace_count"],
        "stale_count": counts["stale_generation_count"],
        "span_violation_count": counts["span_checked_count"] - counts["span_valid_count"],
    }
    if split == "sealed_test":
        sealed_manifest = canonicalize_butler_cj1({"sealed": True, "sample_count": len(row_values)})
        hidden_labels = b"encrypted-hidden-label-artifact-v51"
        attachments[_digest(sealed_manifest)] = sealed_manifest
        attachments[_digest(hidden_labels)] = hidden_labels
        payload.update(
            {
                "calibration_payload_sha256": calibration_digest,
                "sealed_dataset_manifest_sha256": _digest(sealed_manifest),
                "hidden_labels_sha256": _digest(hidden_labels),
            }
        )
    return payload, attachments


def envelope(
    *,
    role: str,
    payload: dict[str, Any],
    key_id: str,
    private_key: Ed25519PrivateKey,
    nonce_byte: int,
    attachments: Mapping[str, bytes] | None = None,
    signed_updates: Mapping[str, Any] | None = None,
    signature_b64u: str | None = None,
) -> EvidenceArtifact:
    payload_bytes = canonicalize_butler_cj1(payload)
    signed = {
        "schema_version": "butler.helper1.evidence-envelope.v1",
        "role": role,
        "key_id": key_id,
        "repository": REPOSITORY,
        "commit_sha": COMMIT,
        "tree_sha": TREE,
        "workspace_id": WORKSPACE,
        "issued_at_epoch_s": NOW - 5,
        "expires_at_epoch_s": NOW + 300,
        "nonce_b64u": b64url(bytes([nonce_byte]) * 16),
        "payload_media_type": ROLE_MEDIA_TYPES[role],
        "payload_sha256": _digest(payload_bytes),
    }
    if signed_updates:
        signed.update(signed_updates)
    signature = signature_b64u or b64url(private_key.sign(EVIDENCE_DOMAIN + canonicalize_butler_cj1(signed)))
    envelope_bytes = canonicalize_butler_cj1(
        {"signed": signed, "signature_algorithm": "Ed25519", "signature_b64u": signature}
    )
    return EvidenceArtifact(
        envelope_bytes=envelope_bytes,
        payload_bytes=payload_bytes,
        attachments_by_digest=tuple(sorted((attachments or {}).items())),
    )


def evidence_set(keys: tuple[Ed25519PrivateKey, ...]) -> list[EvidenceArtifact]:
    evidence, threshold, _ = keys
    threshold_value = threshold_payload()
    threshold_bytes = canonicalize_butler_cj1(threshold_value)
    threshold_digest = _digest(threshold_bytes)
    calibration, calibration_attachments = evaluation_material("calibration", rows("cal"), threshold_digest)
    calibration_digest = _digest(canonicalize_butler_cj1(calibration))
    sealed, sealed_attachments = evaluation_material(
        "sealed_test", rows("sealed"), threshold_digest, calibration_digest=calibration_digest
    )
    values: list[EvidenceArtifact] = []
    for index, role in enumerate(REQUIRED_EVIDENCE_ROLES, start=1):
        attachments: dict[str, bytes]
        if role == "A4_RETRIEVAL_CALIBRATION_RECEIPT":
            payload, attachments = calibration, calibration_attachments
        elif role == "A4_RETRIEVAL_SEALED_TEST_RECEIPT":
            payload, attachments = sealed, sealed_attachments
        else:
            measurement = canonicalize_butler_cj1({"role": role, "passed": True})
            prefix = role.split("_", 1)[0].lower()
            payload = {
                "schema_version": {
                    "A1_STARTUP_COMPOSITION_RECEIPT": "butler.helper1.a1-startup-composition.v1",
                    "A2_SUBJECT_BINDING_RECEIPT": "butler.helper1.a2-subject-binding.v1",
                    "A3_EGRESS_OBSERVATION_RECEIPT": "butler.helper1.a3-egress-observation.v1",
                    "A5_PARSER_ISOLATION_RECEIPT": "butler.helper1.a5-parser-isolation.v1",
                }[role],
                "passed": True,
                "measurement_sha256": _digest(measurement),
            }
            attachments = {_digest(measurement): measurement}
            assert prefix
        values.append(
            envelope(
                role=role,
                payload=payload,
                key_id=EVIDENCE_KEY_ID,
                private_key=evidence,
                nonce_byte=index,
                attachments=attachments,
            )
        )
    threshold_attachments = {
        EVALUATOR_SHA: EVALUATOR_SOURCE,
        ENCODER_SHA: ENCODER_ARTIFACT,
        CORPUS_SHA: CORPUS_MANIFEST,
        INDEX_SHA: INDEX_POLICY,
    }
    values.append(
        envelope(
            role=THRESHOLD_POLICY_ROLE,
            payload=threshold_value,
            key_id=THRESHOLD_KEY_ID,
            private_key=threshold,
            nonce_byte=99,
            attachments=threshold_attachments,
        )
    )
    return values


def evidence_set_digest(values: list[EvidenceArtifact]) -> str:
    return evidence_set_sha256(values)


def activation_authority(activation_key: Ed25519PrivateKey, *, closure_digest: str) -> NativeExecutionAuthority:
    public = public_bytes(activation_key)
    key_id = hashlib.sha256(public).hexdigest()
    unsigned = {
        "schema_version": "butler.helper1.activation-grant.v3",
        "key_id": key_id,
        "subject_commit": COMMIT,
        "subject_tree": TREE,
        "workspace_id": WORKSPACE,
        "generation_id": GENERATION,
        "actions": ["ask", "search"],
        "artifact_digests": [MANIFEST_DIGEST, closure_digest],
        "not_before_epoch_s": NOW - 30,
        "expires_at_epoch_s": NOW + 300,
        "grant_nonce_sha256": "c" * 64,
    }
    signed = {
        **unsigned,
        "signature_b64": base64.b64encode(activation_key.sign(canonicalize_butler_cj1(unsigned))).decode("ascii"),
    }
    return NativeExecutionAuthority(
        public_key_bytes=public,
        expected_public_key_sha256=key_id,
        signed_activation_grant=signed,
        native_signer=lambda _: {},
        clock=lambda: NOW,
    )
