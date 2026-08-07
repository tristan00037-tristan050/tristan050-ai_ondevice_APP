"""Fail-closed Helper1 A1-A5 approval closure.

Evidence envelopes and payloads are transported as separate canonical byte
strings.  Every digest is recomputed from bytes, every signature covers the
fixed BUTLER-CJ-1 signed object, and replay reservation happens once after all
semantic and cross-artifact checks have passed.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .canonical_json import (
    CanonicalJsonError,
    canonicalize_butler_cj1,
    cj1_sha256,
    require_canonical_butler_cj1,
)
from .execution import NativeExecutionAuthority
from .replay_store import ReplayReservation, ReplayStoreError
from .retrieval_policy import (
    DIGEST_RE,
    GIT_OID_RE,
    KEY_ID_RE,
    RetrievalPolicyAuthority,
    RetrievalPolicyAuthorityError,
)

NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
SAFE_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")

REQUIRED_EVIDENCE_ROLES = (
    "A1_STARTUP_COMPOSITION_RECEIPT",
    "A2_SUBJECT_BINDING_RECEIPT",
    "A3_EGRESS_OBSERVATION_RECEIPT",
    "A4_RETRIEVAL_CALIBRATION_RECEIPT",
    "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
    "A5_PARSER_ISOLATION_RECEIPT",
)
THRESHOLD_POLICY_ROLE = "A4_RETRIEVAL_THRESHOLD_POLICY"
KNOWN_ROLES = frozenset((*REQUIRED_EVIDENCE_ROLES, THRESHOLD_POLICY_ROLE))

ROLE_MEDIA_TYPES = {
    "A1_STARTUP_COMPOSITION_RECEIPT": "application/vnd.butler.helper1.a1-startup+json;v=1",
    "A2_SUBJECT_BINDING_RECEIPT": "application/vnd.butler.helper1.a2-subject+json;v=1",
    "A3_EGRESS_OBSERVATION_RECEIPT": "application/vnd.butler.helper1.a3-egress+json;v=1",
    "A4_RETRIEVAL_CALIBRATION_RECEIPT": "application/vnd.butler.helper1.a4-calibration+json;v=1",
    "A4_RETRIEVAL_SEALED_TEST_RECEIPT": "application/vnd.butler.helper1.a4-sealed-test+json;v=1",
    "A4_RETRIEVAL_THRESHOLD_POLICY": "application/vnd.butler.helper1.a4-threshold-policy+json;v=1",
    "A5_PARSER_ISOLATION_RECEIPT": "application/vnd.butler.helper1.a5-parser+json;v=1",
}


class ApprovalState(str, Enum):
    DISABLED = "DISABLED"
    VERIFYING = "VERIFYING"
    A4_VERIFIED = "A4_VERIFIED"
    ALL_EVIDENCE_VERIFIED = "ALL_EVIDENCE_VERIFIED"
    RELEASE_ALLOWED = "RELEASE_ALLOWED"
    ACTIVE = "ACTIVE"


class FailureCode(str, Enum):
    TRUST_POLICY_DISABLED = "TRUST_POLICY_DISABLED"
    AUTHORITY_INVALID = "AUTHORITY_INVALID"
    ACTIVATION_AUTHORITY_INVALID = "ACTIVATION_AUTHORITY_INVALID"
    ACTIVATION_CLOSURE_BINDING_MISMATCH = "ACTIVATION_CLOSURE_BINDING_MISMATCH"
    EVIDENCE_SCHEMA_INVALID = "EVIDENCE_SCHEMA_INVALID"
    EVIDENCE_ROLE_MISSING = "EVIDENCE_ROLE_MISSING"
    EVIDENCE_ROLE_DUPLICATE = "EVIDENCE_ROLE_DUPLICATE"
    EVIDENCE_ROLE_UNKNOWN = "EVIDENCE_ROLE_UNKNOWN"
    EVIDENCE_SUBJECT_MISMATCH = "EVIDENCE_SUBJECT_MISMATCH"
    EVIDENCE_TIME_INVALID = "EVIDENCE_TIME_INVALID"
    EVIDENCE_PAYLOAD_DIGEST_MISMATCH = "EVIDENCE_PAYLOAD_DIGEST_MISMATCH"
    EVIDENCE_ATTACHMENT_MISSING = "EVIDENCE_ATTACHMENT_MISSING"
    EVIDENCE_ATTACHMENT_DIGEST_MISMATCH = "EVIDENCE_ATTACHMENT_DIGEST_MISMATCH"
    EVIDENCE_SIGNATURE_INVALID = "EVIDENCE_SIGNATURE_INVALID"
    EVIDENCE_REPLAY_DETECTED = "EVIDENCE_REPLAY_DETECTED"
    EVIDENCE_SEMANTICS_INVALID = "EVIDENCE_SEMANTICS_INVALID"
    A4_EVIDENCE_MISSING = "A4_EVIDENCE_MISSING"
    THRESHOLD_POLICY_UNSIGNED = "THRESHOLD_POLICY_UNSIGNED"
    A4_THRESHOLD_POLICY_INVALID = "A4_THRESHOLD_POLICY_INVALID"
    A4_METRIC_RECOMPUTE_MISMATCH = "A4_METRIC_RECOMPUTE_MISMATCH"
    A4_STRATA_MISMATCH = "A4_STRATA_MISMATCH"
    A4_ROW_COUNT_MISMATCH = "A4_ROW_COUNT_MISMATCH"
    A4_CROSS_BINDING_MISMATCH = "A4_CROSS_BINDING_MISMATCH"
    A4_THRESHOLD_FAILED = "A4_THRESHOLD_FAILED"
    A4_SEALED_LEAKAGE = "A4_SEALED_LEAKAGE"


@dataclass(frozen=True, slots=True)
class Failure:
    code: FailureCode
    role: str | None = None
    artifact_digest: str | None = None
    field_path: str | None = None

    def sort_key(self) -> tuple[str, str, str, str]:
        return self.role or "", self.code.value, self.artifact_digest or "", self.field_path or ""

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code.value,
            "role": self.role,
            "artifact_digest": self.artifact_digest,
            "field_path": self.field_path,
        }


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """Untrusted wire input. Trust is established only by the closure."""

    envelope_bytes: bytes
    payload_bytes: bytes
    attachments_by_digest: tuple[tuple[str, bytes], ...] = ()

    def __post_init__(self) -> None:
        if type(self.envelope_bytes) is not bytes or type(self.payload_bytes) is not bytes:
            raise ValueError("EVIDENCE_BYTES_REQUIRED")
        if type(self.attachments_by_digest) is not tuple:
            raise ValueError("EVIDENCE_ATTACHMENTS_INVALID")
        seen: set[str] = set()
        for item in self.attachments_by_digest:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or DIGEST_RE.fullmatch(item[0]) is None
                or type(item[1]) is not bytes
                or item[0] in seen
            ):
                raise ValueError("EVIDENCE_ATTACHMENTS_INVALID")
            seen.add(item[0])


@dataclass(frozen=True, slots=True)
class _ParsedEvidence:
    signed: dict[str, Any]
    payload: dict[str, Any]
    signature_b64u: str
    payload_digest: str
    artifact_digest: str
    attachments: dict[str, bytes]

    @property
    def role(self) -> str:
        return self.signed["role"]

    @property
    def key_id(self) -> str:
        return self.signed["key_id"]


def _parse_artifact(value: object) -> _ParsedEvidence:
    if type(value) is not EvidenceArtifact:
        raise ValueError("EVIDENCE_ARTIFACT_TYPE_INVALID")
    try:
        envelope = require_canonical_butler_cj1(value.envelope_bytes)
        payload = require_canonical_butler_cj1(value.payload_bytes)
    except CanonicalJsonError as exc:
        raise ValueError("EVIDENCE_CANONICAL_INVALID") from exc
    if type(envelope) is not dict or set(envelope) != {"signed", "signature_algorithm", "signature_b64u"}:
        raise ValueError("EVIDENCE_SCHEMA_INVALID")
    signed = envelope["signed"]
    if type(signed) is not dict or set(signed) != {
        "schema_version", "role", "key_id", "repository", "commit_sha", "tree_sha",
        "workspace_id", "issued_at_epoch_s", "expires_at_epoch_s", "nonce_b64u",
        "payload_media_type", "payload_sha256",
    }:
        raise ValueError("EVIDENCE_SCHEMA_INVALID")
    role = signed.get("role")
    if (
        signed.get("schema_version") != "butler.helper1.evidence-envelope.v1"
        or type(role) is not str
        or type(signed.get("key_id")) is not str
        or KEY_ID_RE.fullmatch(signed["key_id"]) is None
        or type(signed.get("repository")) is not str
        or SAFE_TEXT_RE.fullmatch(signed["repository"]) is None
        or type(signed.get("commit_sha")) is not str
        or GIT_OID_RE.fullmatch(signed["commit_sha"]) is None
        or type(signed.get("tree_sha")) is not str
        or GIT_OID_RE.fullmatch(signed["tree_sha"]) is None
        or type(signed.get("workspace_id")) is not str
        or type(signed.get("issued_at_epoch_s")) is not int
        or type(signed.get("expires_at_epoch_s")) is not int
        or type(signed.get("nonce_b64u")) is not str
        or NONCE_RE.fullmatch(signed["nonce_b64u"]) is None
        or signed.get("payload_media_type") != ROLE_MEDIA_TYPES.get(role)
        or type(signed.get("payload_sha256")) is not str
        or DIGEST_RE.fullmatch(signed["payload_sha256"]) is None
        or envelope.get("signature_algorithm") != "Ed25519"
        or type(envelope.get("signature_b64u")) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{86}", envelope["signature_b64u"]) is None
        or type(payload) is not dict
    ):
        raise ValueError("EVIDENCE_SCHEMA_INVALID")
    payload_digest = hashlib.sha256(value.payload_bytes).hexdigest()
    attachments = dict(value.attachments_by_digest)
    artifact_digest = hashlib.sha256(
        canonicalize_butler_cj1(
            {
                "envelope_sha256": hashlib.sha256(value.envelope_bytes).hexdigest(),
                "payload_sha256": payload_digest,
                "attachment_sha256s": sorted(attachments),
            }
        )
    ).hexdigest()
    return _ParsedEvidence(
        signed=dict(signed),
        payload=dict(payload),
        signature_b64u=envelope["signature_b64u"],
        payload_digest=payload_digest,
        artifact_digest=artifact_digest,
        attachments=attachments,
    )


_VERDICT_TOKEN = object()
_VERDICT_REGISTRY: dict[int, str] = {}
_VERDICT_LOCK = threading.Lock()


class ClosureVerdict:
    __slots__ = ("state", "failures", "evidence_set_sha256", "policy_sha256", "policy_epoch", "verified_roles")

    def __init_subclass__(cls, **_: Any) -> None:
        raise TypeError("CLOSURE_VERDICT_FINAL")

    def __init__(
        self,
        token: object,
        *,
        state: ApprovalState,
        failures: tuple[Failure, ...],
        evidence_set_sha256: str,
        policy_sha256: str,
        policy_epoch: int,
        verified_roles: tuple[str, ...],
    ) -> None:
        if token is not _VERDICT_TOKEN:
            raise ValueError("CLOSURE_VERDICT_FORGED")
        for name, value in {
            "state": state, "failures": failures, "evidence_set_sha256": evidence_set_sha256,
            "policy_sha256": policy_sha256, "policy_epoch": policy_epoch,
            "verified_roles": verified_roles,
        }.items():
            object.__setattr__(self, name, value)
        with _VERDICT_LOCK:
            _VERDICT_REGISTRY[id(self)] = self.capability_digest

    def __setattr__(self, _: str, __: object) -> None:
        raise AttributeError("CLOSURE_VERDICT_IMMUTABLE")

    def __copy__(self) -> None:
        raise TypeError("CLOSURE_VERDICT_NOT_COPYABLE")

    def __deepcopy__(self, _: object) -> None:
        raise TypeError("CLOSURE_VERDICT_NOT_COPYABLE")

    def __reduce__(self) -> None:
        raise TypeError("CLOSURE_VERDICT_NOT_SERIALIZABLE")

    @property
    def capability_digest(self) -> str:
        return hashlib.sha256(
            canonicalize_butler_cj1(
                {
                    "state": self.state.value,
                    "failures": [item.to_dict() for item in self.failures],
                    "evidence_set_sha256": self.evidence_set_sha256,
                    "policy_sha256": self.policy_sha256,
                    "policy_epoch": self.policy_epoch,
                    "verified_roles": list(self.verified_roles),
                }
            )
        ).hexdigest()

    @property
    def release_allowed(self) -> bool:
        if self.state is not ApprovalState.RELEASE_ALLOWED or self.failures:
            return False
        with _VERDICT_LOCK:
            return _VERDICT_REGISTRY.get(id(self)) == self.capability_digest

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "verified": not self.failures,
            "failure_count": len(self.failures),
            "failures": [item.to_dict() for item in self.failures],
            "evidence_set_sha256": self.evidence_set_sha256,
            "policy_sha256": self.policy_sha256,
            "policy_epoch": self.policy_epoch,
            "verified_roles": list(self.verified_roles),
            "product_release_allowed": False,
            "runtime_activation_allowed": False,
            "production_claim_allowed": False,
        }


def ppm(numerator: int, denominator: int) -> int:
    if type(numerator) is not int or type(denominator) is not int or numerator < 0 or denominator <= 0 or numerator > denominator:
        raise ValueError("A4_METRIC_DENOMINATOR_INVALID")
    return (numerator * 1_000_000 + denominator // 2) // denominator


_ROW_KEYS = {
    "query_id", "stratum", "answerable", "predicted_abstention", "relevant_count",
    "retrieved_relevant_count", "first_relevant_rank", "retrieved_count",
    "wrong_workspace_count", "stale_generation_count", "span_valid_count", "span_checked_count",
}
_LABEL_KEYS = {"query_id", "stratum", "answerable", "relevant_count"}
_PREDICTION_KEYS = _ROW_KEYS - {"stratum", "answerable", "relevant_count"}


def recompute_a4_rows(rows: object) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    if type(rows) is not list or not rows:
        raise ValueError("A4_ROWS_INVALID")
    counts = {
        "sample_count": 0, "answerable_count": 0, "unanswerable_count": 0,
        "predicted_abstention_count": 0, "correct_abstention_count": 0,
        "false_abstention_count": 0, "relevant_count": 0,
        "retrieved_relevant_count": 0, "retrieved_count": 0,
        "wrong_workspace_count": 0, "stale_generation_count": 0,
        "span_valid_count": 0, "span_checked_count": 0,
    }
    strata: dict[str, int] = {}
    query_ids: set[str] = set()
    for row in rows:
        if type(row) is not dict or set(row) != _ROW_KEYS:
            raise ValueError("A4_ROW_SCHEMA_INVALID")
        query_id, stratum = row["query_id"], row["stratum"]
        answerable, abstain = row["answerable"], row["predicted_abstention"]
        if (
            type(query_id) is not str or not query_id or query_id in query_ids
            or type(stratum) is not str or not stratum
            or type(answerable) is not bool or type(abstain) is not bool
        ):
            raise ValueError("A4_ROW_SCHEMA_INVALID")
        query_ids.add(query_id)
        integer_names = _ROW_KEYS - {"query_id", "stratum", "answerable", "predicted_abstention", "first_relevant_rank"}
        if any(type(row[name]) is not int or row[name] < 0 for name in integer_names):
            raise ValueError("A4_ROW_COUNT_INVALID")
        first_rank = row["first_relevant_rank"]
        if first_rank is not None and (type(first_rank) is not int or first_rank < 1):
            raise ValueError("A4_ROW_RANK_INVALID")
        relevant = row["relevant_count"]
        retrieved_relevant = row["retrieved_relevant_count"]
        retrieved = row["retrieved_count"]
        if (
            answerable != (relevant > 0)
            or retrieved_relevant > relevant
            or retrieved_relevant > retrieved
            or (retrieved_relevant == 0) != (first_rank is None)
            or row["wrong_workspace_count"] > retrieved
            or row["stale_generation_count"] > retrieved
            or row["span_valid_count"] > row["span_checked_count"]
            or abstain != (retrieved == 0)
        ):
            raise ValueError("A4_ROW_CONSISTENCY_INVALID")
        counts["sample_count"] += 1
        counts["answerable_count"] += int(answerable)
        counts["unanswerable_count"] += int(not answerable)
        counts["predicted_abstention_count"] += int(abstain)
        counts["correct_abstention_count"] += int(abstain and not answerable)
        counts["false_abstention_count"] += int(abstain and answerable)
        for name in (
            "relevant_count", "retrieved_relevant_count", "retrieved_count",
            "wrong_workspace_count", "stale_generation_count", "span_valid_count", "span_checked_count",
        ):
            counts[name] += row[name]
        strata[stratum] = strata.get(stratum, 0) + 1
    metrics = {
        "retrieval_recall_ppm": ppm(counts["retrieved_relevant_count"], counts["relevant_count"]),
        "abstention_precision_ppm": ppm(counts["correct_abstention_count"], counts["predicted_abstention_count"]),
        "abstention_recall_ppm": ppm(counts["correct_abstention_count"], counts["unanswerable_count"]),
        "wrong_workspace_rate_ppm": ppm(counts["wrong_workspace_count"], max(1, counts["retrieved_count"])),
        "stale_generation_rate_ppm": ppm(counts["stale_generation_count"], max(1, counts["retrieved_count"])),
        "evidence_span_validity_ppm": ppm(counts["span_valid_count"], counts["span_checked_count"]),
    }
    return counts, metrics, dict(sorted(strata.items()))


def _failure(code: FailureCode, item: _ParsedEvidence | None, field: str | None = None) -> Failure:
    return Failure(code, item.role if item else None, item.artifact_digest if item else None, field)


def _attachment(item: _ParsedEvidence, digest: object, field: str, failures: list[Failure]) -> bytes | None:
    if type(digest) is not str or DIGEST_RE.fullmatch(digest) is None:
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, field))
        return None
    raw = item.attachments.get(digest)
    if raw is None:
        failures.append(_failure(FailureCode.EVIDENCE_ATTACHMENT_MISSING, item, field))
        return None
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
        failures.append(_failure(FailureCode.EVIDENCE_ATTACHMENT_DIGEST_MISMATCH, item, field))
        return None
    return raw


def _attachment_json(item: _ParsedEvidence, digest: object, field: str, failures: list[Failure]) -> object | None:
    raw = _attachment(item, digest, field, failures)
    if raw is None:
        return None
    try:
        return require_canonical_butler_cj1(raw)
    except CanonicalJsonError:
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, field))
        return None


def _generic_semantics(item: _ParsedEvidence) -> list[Failure]:
    expected_schema = {
        "A1_STARTUP_COMPOSITION_RECEIPT": "butler.helper1.a1-startup-composition.v1",
        "A2_SUBJECT_BINDING_RECEIPT": "butler.helper1.a2-subject-binding.v1",
        "A3_EGRESS_OBSERVATION_RECEIPT": "butler.helper1.a3-egress-observation.v1",
        "A5_PARSER_ISOLATION_RECEIPT": "butler.helper1.a5-parser-isolation.v1",
    }.get(item.role)
    if expected_schema is None:
        return []
    failures: list[Failure] = []
    payload = item.payload
    if set(payload) != {"schema_version", "passed", "measurement_sha256"} or payload.get("schema_version") != expected_schema or payload.get("passed") is not True:
        return [_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item)]
    _attachment(item, payload.get("measurement_sha256"), "measurement_sha256", failures)
    return failures


def _join_a4_rows(item: _ParsedEvidence, failures: list[Failure]) -> list[dict[str, Any]] | None:
    labels = _attachment_json(item, item.payload.get("label_rows_sha256"), "label_rows_sha256", failures)
    predictions = _attachment_json(item, item.payload.get("prediction_rows_sha256"), "prediction_rows_sha256", failures)
    if type(labels) is not list or type(predictions) is not list:
        if labels is not None and predictions is not None:
            failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, "rows"))
        return None
    if len(labels) != len(predictions) or not labels:
        failures.append(_failure(FailureCode.A4_ROW_COUNT_MISMATCH, item, "rows"))
        return None
    by_prediction: dict[str, dict[str, Any]] = {}
    try:
        for row in predictions:
            if type(row) is not dict or set(row) != _PREDICTION_KEYS or type(row.get("query_id")) is not str or row["query_id"] in by_prediction:
                raise ValueError
            by_prediction[row["query_id"]] = row
        combined: list[dict[str, Any]] = []
        seen: set[str] = set()
        for label in labels:
            if type(label) is not dict or set(label) != _LABEL_KEYS or type(label.get("query_id")) is not str or label["query_id"] in seen:
                raise ValueError
            seen.add(label["query_id"])
            prediction = by_prediction.get(label["query_id"])
            if prediction is None:
                raise ValueError
            combined.append({**label, **prediction})
        if seen != set(by_prediction):
            raise ValueError
    except ValueError:
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, "rows"))
        return None
    return combined


_A4_COMMON_KEYS = {
    "schema_version", "evaluator_version", "evaluator_source_sha256",
    "encoder_provider", "encoder_model", "encoder_revision", "encoder_artifact_sha256",
    "corpus_manifest_sha256", "split_inventory_sha256", "group_inventory_sha256",
    "index_manifest_policy_sha256", "threshold_policy_sha256",
    "grounding_threshold_ppm", "abstention_threshold_ppm", "sample_count",
    "required_strata", "strata_counts", "prediction_rows_sha256", "label_rows_sha256",
    "evaluation_report_sha256", "counts", "metrics_ppm", "wrong_workspace_count",
    "stale_count", "span_violation_count",
}


def _verify_a4_payload(item: _ParsedEvidence) -> tuple[list[Failure], tuple[dict[str, int], dict[str, int], dict[str, int]] | None]:
    failures: list[Failure] = []
    sealed = item.role == "A4_RETRIEVAL_SEALED_TEST_RECEIPT"
    expected_keys = _A4_COMMON_KEYS | ({"calibration_payload_sha256", "sealed_dataset_manifest_sha256", "hidden_labels_sha256"} if sealed else set())
    expected_schema = "butler.helper1.retrieval-sealed-test-receipt.v1" if sealed else "butler.helper1.retrieval-calibration-receipt.v1"
    payload = item.payload
    if set(payload) != expected_keys or payload.get("schema_version") != expected_schema:
        return [_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item)], None
    text_fields = ("evaluator_version", "encoder_provider", "encoder_model", "encoder_revision")
    digest_fields = (
        "evaluator_source_sha256", "encoder_artifact_sha256", "corpus_manifest_sha256",
        "split_inventory_sha256", "group_inventory_sha256", "index_manifest_policy_sha256",
        "threshold_policy_sha256", "prediction_rows_sha256", "label_rows_sha256",
        "evaluation_report_sha256",
    ) + (("calibration_payload_sha256", "sealed_dataset_manifest_sha256", "hidden_labels_sha256") if sealed else ())
    if any(type(payload.get(name)) is not str or SAFE_TEXT_RE.fullmatch(payload[name]) is None for name in text_fields):
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, "identity"))
    if any(type(payload.get(name)) is not str or DIGEST_RE.fullmatch(payload[name]) is None for name in digest_fields):
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, "digest"))
        return failures, None
    for name in (
        "evaluator_source_sha256", "encoder_artifact_sha256", "corpus_manifest_sha256",
        "split_inventory_sha256", "group_inventory_sha256", "index_manifest_policy_sha256",
    ) + (("sealed_dataset_manifest_sha256", "hidden_labels_sha256") if sealed else ()):
        _attachment(item, payload[name], name, failures)
    for name in ("grounding_threshold_ppm", "abstention_threshold_ppm"):
        if type(payload.get(name)) is not int or not 0 <= payload[name] <= 1_000_000:
            failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, name))
    required_strata = payload.get("required_strata")
    if type(required_strata) is not list or not required_strata or any(type(value) is not str or not value for value in required_strata) or len(set(required_strata)) != len(required_strata):
        failures.append(_failure(FailureCode.A4_STRATA_MISMATCH, item, "required_strata"))
    rows = _join_a4_rows(item, failures)
    if rows is None:
        return failures, None
    try:
        counts, metrics, strata = recompute_a4_rows(rows)
    except ValueError:
        failures.append(_failure(FailureCode.EVIDENCE_SEMANTICS_INVALID, item, "rows"))
        return failures, None
    if payload.get("sample_count") != counts["sample_count"]:
        failures.append(_failure(FailureCode.A4_ROW_COUNT_MISMATCH, item, "sample_count"))
    if payload.get("counts") != counts or payload.get("metrics_ppm") != metrics:
        failures.append(_failure(FailureCode.A4_METRIC_RECOMPUTE_MISMATCH, item, "metrics_ppm"))
    if payload.get("strata_counts") != strata:
        failures.append(_failure(FailureCode.A4_STRATA_MISMATCH, item, "strata_counts"))
    if payload.get("wrong_workspace_count") != counts["wrong_workspace_count"] or payload.get("stale_count") != counts["stale_generation_count"] or payload.get("span_violation_count") != counts["span_checked_count"] - counts["span_valid_count"]:
        failures.append(_failure(FailureCode.A4_METRIC_RECOMPUTE_MISMATCH, item, "raw_counts"))
    expected_report = {
        "schema_version": "butler.helper1.retrieval-evaluation-report.v1",
        "counts": counts,
        "metrics_ppm": metrics,
        "strata_counts": strata,
    }
    report = _attachment_json(item, payload["evaluation_report_sha256"], "evaluation_report_sha256", failures)
    if report is not None and report != expected_report:
        failures.append(_failure(FailureCode.A4_METRIC_RECOMPUTE_MISMATCH, item, "evaluation_report_sha256"))
    if sealed and any(counts[name] != 0 for name in ("wrong_workspace_count", "stale_generation_count")):
        failures.append(_failure(FailureCode.A4_SEALED_LEAKAGE, item))
    if sealed and counts["span_checked_count"] != counts["span_valid_count"]:
        failures.append(_failure(FailureCode.A4_SEALED_LEAKAGE, item, "span_violation_count"))
    return failures, (counts, metrics, strata)


_THRESHOLD_KEYS = {
    "schema_version", "policy_epoch", "evaluator_source_sha256",
    "encoder_provider", "encoder_model", "encoder_revision", "encoder_artifact_sha256",
    "corpus_manifest_sha256", "index_manifest_policy_sha256",
    "grounding_threshold_ppm", "abstention_threshold_ppm", "required_strata",
    "minimum_sample_count", "minimum_per_stratum_count", "minimum_metrics_ppm",
    "maximum_metrics_ppm", "issued_at_epoch_s", "expires_at_epoch_s",
}


def _threshold_semantics(item: _ParsedEvidence) -> list[Failure]:
    payload = item.payload
    failures: list[Failure] = []
    if set(payload) != _THRESHOLD_KEYS or payload.get("schema_version") != "butler.helper1.retrieval-threshold-policy.v1":
        return [_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item)]
    for name in ("evaluator_source_sha256", "encoder_artifact_sha256", "corpus_manifest_sha256", "index_manifest_policy_sha256"):
        _attachment(item, payload.get(name), name, failures)
    if payload.get("issued_at_epoch_s") != item.signed["issued_at_epoch_s"] or payload.get("expires_at_epoch_s") != item.signed["expires_at_epoch_s"]:
        failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, "time_binding"))
    for name in ("policy_epoch", "minimum_sample_count", "minimum_per_stratum_count"):
        if type(payload.get(name)) is not int or payload[name] < 1:
            failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, name))
    for name in ("grounding_threshold_ppm", "abstention_threshold_ppm"):
        if type(payload.get(name)) is not int or not 0 <= payload[name] <= 1_000_000:
            failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, name))
    strata = payload.get("required_strata")
    if type(strata) is not list or not strata or any(type(value) is not str or not value for value in strata) or len(set(strata)) != len(strata):
        failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, "required_strata"))
    for name in ("minimum_metrics_ppm", "maximum_metrics_ppm"):
        values = payload.get(name)
        if type(values) is not dict or not values or any(type(key) is not str or type(value) is not int or not 0 <= value <= 1_000_000 for key, value in values.items()):
            failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, name))
    for name in ("encoder_provider", "encoder_model", "encoder_revision"):
        if type(payload.get(name)) is not str or SAFE_TEXT_RE.fullmatch(payload[name]) is None:
            failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, item, name))
    return failures


def _cross_check_a4(
    authority: RetrievalPolicyAuthority,
    threshold: _ParsedEvidence,
    calibration: _ParsedEvidence,
    sealed: _ParsedEvidence,
    results: dict[str, tuple[dict[str, int], dict[str, int], dict[str, int]] | None],
) -> list[Failure]:
    failures: list[Failure] = []
    snapshot = authority.snapshot
    policy, left, right = threshold.payload, calibration.payload, sealed.payload
    if policy.get("policy_epoch") != snapshot.policy_epoch:
        failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, threshold, "policy_epoch"))
    if any(payload.get("threshold_policy_sha256") != threshold.payload_digest for payload in (left, right)):
        failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, sealed, "threshold_policy_sha256"))
    if right.get("calibration_payload_sha256") != calibration.payload_digest:
        failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, sealed, "calibration_payload_sha256"))
    identity_fields = (
        "evaluator_source_sha256", "encoder_provider", "encoder_model", "encoder_revision",
        "encoder_artifact_sha256", "corpus_manifest_sha256", "index_manifest_policy_sha256",
        "grounding_threshold_ppm", "abstention_threshold_ppm", "required_strata",
    )
    for field in identity_fields:
        if left.get(field) != right.get(field) or left.get(field) != policy.get(field):
            failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, sealed, field))
    if left.get("split_inventory_sha256") == right.get("split_inventory_sha256") or left.get("group_inventory_sha256") == right.get("group_inventory_sha256"):
        failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, sealed, "split_binding"))
    expected = {
        "evaluator_source_sha256": snapshot.expected_evaluator_source_sha256,
        "encoder_provider": snapshot.expected_encoder.provider if snapshot.expected_encoder else None,
        "encoder_model": snapshot.expected_encoder.model if snapshot.expected_encoder else None,
        "encoder_revision": snapshot.expected_encoder.revision if snapshot.expected_encoder else None,
        "encoder_artifact_sha256": snapshot.expected_encoder.artifact_sha256 if snapshot.expected_encoder else None,
        "corpus_manifest_sha256": snapshot.expected_corpus_manifest_sha256,
        "index_manifest_policy_sha256": snapshot.expected_index_manifest_policy_sha256,
        "grounding_threshold_ppm": snapshot.expected_grounding_threshold_ppm,
        "abstention_threshold_ppm": snapshot.expected_abstention_threshold_ppm,
        "required_strata": sorted(snapshot.required_strata),
    }
    for field, expected_value in expected.items():
        if policy.get(field) != expected_value:
            failures.append(_failure(FailureCode.A4_CROSS_BINDING_MISMATCH, threshold, field))
    if policy.get("minimum_sample_count", 0) < snapshot.minimum_sample_count or policy.get("minimum_per_stratum_count", 0) < snapshot.minimum_per_stratum_count:
        failures.append(_failure(FailureCode.A4_THRESHOLD_POLICY_INVALID, threshold, "minimum_sample_count"))
    for item in (calibration, sealed):
        result = results.get(item.role)
        if result is None:
            continue
        counts, metrics, strata = result
        if counts["sample_count"] < policy.get("minimum_sample_count", 2**63 - 1):
            failures.append(_failure(FailureCode.A4_THRESHOLD_FAILED, item, "sample_count"))
        for stratum in policy.get("required_strata", []):
            if strata.get(stratum, 0) < policy.get("minimum_per_stratum_count", 2**63 - 1):
                failures.append(_failure(FailureCode.A4_THRESHOLD_FAILED, item, "strata_counts"))
        for metric, minimum in policy.get("minimum_metrics_ppm", {}).items():
            if metrics.get(metric, -1) < minimum:
                failures.append(_failure(FailureCode.A4_THRESHOLD_FAILED, item, metric))
        for metric, maximum in policy.get("maximum_metrics_ppm", {}).items():
            if metrics.get(metric, 1_000_001) > maximum:
                failures.append(_failure(FailureCode.A4_THRESHOLD_FAILED, item, metric))
    return failures


def evidence_set_sha256(values: Iterable[EvidenceArtifact]) -> str:
    parsed = tuple(_parse_artifact(value) for value in values)
    return cj1_sha256(sorted(item.artifact_digest for item in parsed))


def _mint_verdict(
    authority: RetrievalPolicyAuthority,
    state: ApprovalState,
    failures: Iterable[Failure],
    parsed: Iterable[_ParsedEvidence],
    verified_roles: Iterable[str],
) -> ClosureVerdict:
    snapshot = authority.snapshot
    return ClosureVerdict(
        _VERDICT_TOKEN,
        state=state,
        failures=tuple(sorted(set(failures), key=Failure.sort_key)),
        evidence_set_sha256=cj1_sha256(sorted(item.artifact_digest for item in parsed)),
        policy_sha256=snapshot.digest,
        policy_epoch=snapshot.policy_epoch,
        verified_roles=tuple(sorted(set(verified_roles))),
    )


def evaluate_product_closure(
    authority: RetrievalPolicyAuthority,
    activation_authority: NativeExecutionAuthority,
    artifact_values: Iterable[object],
) -> ClosureVerdict:
    """Verify one complete evidence set and reserve every nonce atomically."""
    if type(authority) is not RetrievalPolicyAuthority or not authority.is_current():
        raise ValueError("RETRIEVAL_AUTHORITY_INVALID")
    snapshot = authority.snapshot
    if not snapshot.enabled:
        return _mint_verdict(authority, ApprovalState.DISABLED, (Failure(FailureCode.TRUST_POLICY_DISABLED),), (), ())
    failures: list[Failure] = []
    parsed: list[_ParsedEvidence] = []
    for value in artifact_values:
        try:
            parsed.append(_parse_artifact(value))
        except (ValueError, CanonicalJsonError):
            failures.append(Failure(FailureCode.EVIDENCE_SCHEMA_INVALID))
    by_role: dict[str, list[_ParsedEvidence]] = {}
    for item in parsed:
        by_role.setdefault(item.role, []).append(item)
        if item.role not in KNOWN_ROLES:
            failures.append(_failure(FailureCode.EVIDENCE_ROLE_UNKNOWN, item))
    for role in (*REQUIRED_EVIDENCE_ROLES, THRESHOLD_POLICY_ROLE):
        matches = by_role.get(role, [])
        if not matches:
            if role in {
                "A4_RETRIEVAL_CALIBRATION_RECEIPT",
                "A4_RETRIEVAL_SEALED_TEST_RECEIPT",
            }:
                code = FailureCode.A4_EVIDENCE_MISSING
            elif role == THRESHOLD_POLICY_ROLE:
                code = FailureCode.THRESHOLD_POLICY_UNSIGNED
            else:
                code = FailureCode.EVIDENCE_ROLE_MISSING
            failures.append(Failure(code, role=role))
        elif len(matches) != 1:
            failures.append(Failure(FailureCode.EVIDENCE_ROLE_DUPLICATE, role=role))

    grant = activation_authority.grant if type(activation_authority) is NativeExecutionAuthority else None
    if grant is None or activation_authority.is_production_authority is not True:
        failures.append(Failure(FailureCode.ACTIVATION_AUTHORITY_INVALID))
    subject = snapshot.subject
    if subject is None:
        failures.append(Failure(FailureCode.AUTHORITY_INVALID))
    elif grant is not None and (
        grant.subject_commit != subject.commit_sha
        or grant.subject_tree != subject.tree_sha
        or grant.workspace_id != subject.workspace_id
    ):
        failures.append(Failure(FailureCode.ACTIVATION_AUTHORITY_INVALID))
    now = authority.now()
    verified_roles: list[str] = []
    a4_results: dict[str, tuple[dict[str, int], dict[str, int], dict[str, int]] | None] = {}
    for item in parsed:
        signed = item.signed
        individual_failures = 0
        if not hmac.compare_digest(item.payload_digest, signed["payload_sha256"]):
            failures.append(_failure(FailureCode.EVIDENCE_PAYLOAD_DIGEST_MISMATCH, item))
            individual_failures += 1
        if subject is not None and (
            signed["repository"] != snapshot.repository
            or signed["commit_sha"] != subject.commit_sha
            or signed["tree_sha"] != subject.tree_sha
            or signed["workspace_id"] != subject.workspace_id
        ):
            failures.append(_failure(FailureCode.EVIDENCE_SUBJECT_MISMATCH, item))
            individual_failures += 1
        issued, expires = signed["issued_at_epoch_s"], signed["expires_at_epoch_s"]
        if (
            not issued < expires
            or issued > now + snapshot.max_future_skew_seconds
            or now >= expires
            or expires - issued > snapshot.max_evidence_age_seconds
        ):
            failures.append(_failure(FailureCode.EVIDENCE_TIME_INVALID, item))
            individual_failures += 1
        try:
            authority.verify_signature(
                key_id=item.key_id,
                role=item.role,
                signed=signed,
                signature_b64u=item.signature_b64u,
                now_epoch_s=now,
            )
        except RetrievalPolicyAuthorityError:
            failures.append(_failure(FailureCode.EVIDENCE_SIGNATURE_INVALID, item))
            individual_failures += 1
        before = len(failures)
        failures.extend(_generic_semantics(item))
        if item.role in {"A4_RETRIEVAL_CALIBRATION_RECEIPT", "A4_RETRIEVAL_SEALED_TEST_RECEIPT"}:
            item_failures, result = _verify_a4_payload(item)
            failures.extend(item_failures)
            a4_results[item.role] = result
        elif item.role == THRESHOLD_POLICY_ROLE:
            failures.extend(_threshold_semantics(item))
        individual_failures += len(failures) - before
        if individual_failures == 0:
            verified_roles.append(item.role)

    unique = {role: items[0] for role, items in by_role.items() if len(items) == 1}
    required = set(REQUIRED_EVIDENCE_ROLES) | {THRESHOLD_POLICY_ROLE}
    if required <= set(unique):
        failures.extend(
            _cross_check_a4(
                authority,
                unique[THRESHOLD_POLICY_ROLE],
                unique["A4_RETRIEVAL_CALIBRATION_RECEIPT"],
                unique["A4_RETRIEVAL_SEALED_TEST_RECEIPT"],
                a4_results,
            )
        )
    current_evidence_set = cj1_sha256(sorted(item.artifact_digest for item in parsed))
    if grant is not None and current_evidence_set not in grant.artifact_digests:
        failures.append(Failure(FailureCode.ACTIVATION_CLOSURE_BINDING_MISMATCH))
    if not failures:
        reservations = tuple(
            ReplayReservation(
                policy_sha256=snapshot.digest,
                key_id=item.key_id,
                nonce=item.signed["nonce_b64u"],
                expires_at_epoch_s=item.signed["expires_at_epoch_s"],
            )
            for item in parsed
        )
        try:
            authority.reserve(reservations, now)
        except ReplayStoreError as exc:
            if str(exc) != "EVIDENCE_REPLAY_DETECTED":
                raise
            failures.append(Failure(FailureCode.EVIDENCE_REPLAY_DETECTED))
        except RetrievalPolicyAuthorityError:
            failures.append(Failure(FailureCode.AUTHORITY_INVALID))
    if failures:
        a4_roles = {THRESHOLD_POLICY_ROLE, "A4_RETRIEVAL_CALIBRATION_RECEIPT", "A4_RETRIEVAL_SEALED_TEST_RECEIPT"}
        state = ApprovalState.A4_VERIFIED if all(failure.role not in a4_roles for failure in failures) else ApprovalState.VERIFYING
    else:
        state = ApprovalState.RELEASE_ALLOWED if authority.is_production_authority else ApprovalState.ALL_EVIDENCE_VERIFIED
    return _mint_verdict(authority, state, failures, parsed, verified_roles)
