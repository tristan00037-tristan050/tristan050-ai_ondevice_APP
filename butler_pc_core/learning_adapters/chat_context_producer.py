from __future__ import annotations

import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from butler_pc_core.learning_core.runner import LearningIntakeRunner

from .producer_common import (
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
    source_refs_from_mapping,
    str_field,
    validate_digest_or_drop,
)

PRODUCER_VERSION = "chat_context_producer.v1.0.0"
TARGET_KIND = "chat_context"
LEARNING_SOURCE_TYPE = "verified_chat_context"
ALLOWED_CHAT_SOURCE_REF_TYPES = frozenset({"usage_log", "approval"})
ALLOWED_VERIFIED_BY = frozenset(
    {
        "group_a",
        "integrated_learning_verifier",
        "privacy_officer",
        "security_reviewer",
    }
)
ALLOWED_DROP_REASONS = frozenset(
    {
        "CHAT_CONTEXT_DISABLED",
        "BUSINESS_CONFIRMATION_REQUIRED",
        "MANAGER_APPROVAL_REQUIRED",
        "SHADOW_EVAL_CASES_TOO_LOW",
        "PII_NOT_ZERO",
        "FALSE_LEARNING_NOT_ZERO",
        "CONTEXT_DIGEST_INVALID",
        "EVIDENCE_DIGEST_INVALID",
        "VERIFIED_BY_INVALID",
        "VERIFIED_AT_INVALID",
        "EVIDENCE_REF_INVALID",
        "EVIDENCE_REPORT_BINDING_REQUIRED",
        "EVIDENCE_REPORT_BINDING_INVALID",
        "FIXTURE_MODE_FORBIDDEN",
        "RUN_MODE_INVALID",
        "SOURCE_REF_INVALID",
        "SCHEMA_KEYS_INVALID",
    }
)
ALLOWED_RUN_MODES = frozenset({"production", "integration", "fixture_test"})
POLLUTING_MODE_KEYS = frozenset({"fixture_mode", "run_mode"})
SHADOW_EVAL_LABELS = frozenset({"LEARN", "EXCLUDE", "BLOCK", "DROP"})
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
EVIDENCE_REF_ALLOW_RE = re.compile(
    r"^(?:digest-only-fixture|sha256:[0-9a-f]{64}|(?:vault|keyring)://butler/evidence/[A-Za-z0-9._=-]{16,128})$"
)
EVIDENCE_REF_DENY_RE = re.compile(
    r"(?:^/|^[A-Za-z]:\\|\\\\|\.\.|\s|https?://|file://|s3://|gs://|/Users/|/home/|~|@)"
)
PAYLOAD_KEYS = frozenset(
    {
        "explicit_business_confirmation",
        "manager_or_admin_approved",
        "shadow_eval_cases",
        "pii_zero",
        "false_learning_zero",
        "context_digest",
    }
)


class ChatContextProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class ChatContextLearningArtifact:
    explicit_business_confirmation: bool
    manager_or_admin_approved: bool
    shadow_eval_cases: int
    pii_zero: bool
    false_learning_zero: bool
    context_digest: str
    expected_effect_digest: str
    verified_by: str
    verified_at: str
    evidence_ref: str
    evidence_digest: str
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    evidence_report_sha256: str | None = None


def _fail(code: str) -> None:
    raise ChatContextProducerError(code)


def _require_plain_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or value == "" or value.strip() != value:
        _fail(code)
    return value


def validate_verified_by(value: Any) -> str:
    verified_by = _require_plain_string(value, "VERIFIED_BY_INVALID")
    if verified_by not in ALLOWED_VERIFIED_BY:
        _fail("VERIFIED_BY_INVALID")
    return verified_by


def validate_verified_at(value: Any) -> str:
    verified_at = _require_plain_string(value, "VERIFIED_AT_INVALID")
    if not RFC3339_UTC_RE.fullmatch(verified_at):
        _fail("VERIFIED_AT_INVALID")
    try:
        datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _fail("VERIFIED_AT_INVALID")
    return verified_at


def _normalize_run_mode(run_mode: str | None) -> str:
    if run_mode is None:
        return "production"
    if not isinstance(run_mode, str) or run_mode not in ALLOWED_RUN_MODES:
        _fail("RUN_MODE_INVALID")
    return run_mode


def _reject_runtime_mode_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in POLLUTING_MODE_KEYS:
                _fail("FIXTURE_MODE_FORBIDDEN")
            _reject_runtime_mode_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_runtime_mode_keys(child)


def validate_evidence_ref(value: Any, *, run_mode: str) -> str:
    evidence_ref = _require_plain_string(value, "EVIDENCE_REF_INVALID")
    if evidence_ref == "digest-only-fixture" and run_mode != "fixture_test":
        _fail("EVIDENCE_REF_INVALID")
    if EVIDENCE_REF_DENY_RE.search(evidence_ref) or not EVIDENCE_REF_ALLOW_RE.fullmatch(evidence_ref):
        _fail("EVIDENCE_REF_INVALID")
    return evidence_ref


def _canonical_digest(value: str) -> str:
    return value.lower()


def _require_evidence_digest(raw_value: Any, *, context_digest: str) -> str:
    value = _require_plain_string(raw_value, "EVIDENCE_DIGEST_INVALID")
    try:
        digest = validate_digest_or_drop(value, "EVIDENCE")
    except ProducerInputError:
        _fail("EVIDENCE_DIGEST_INVALID")
    if _canonical_digest(digest) == _canonical_digest(context_digest):
        _fail("EVIDENCE_DIGEST_INVALID")
    return digest


def _validate_evidence_report_binding(raw_value: Any, *, evidence_digest: str, run_mode: str) -> str | None:
    if raw_value is None:
        if run_mode == "fixture_test":
            return None
        _fail("EVIDENCE_REPORT_BINDING_REQUIRED")
    value = _require_plain_string(raw_value, "EVIDENCE_REPORT_BINDING_INVALID")
    try:
        report_digest = validate_digest_or_drop(value, "EVIDENCE")
    except ProducerInputError:
        _fail("EVIDENCE_REPORT_BINDING_INVALID")
    if _canonical_digest(report_digest) != _canonical_digest(evidence_digest):
        _fail("EVIDENCE_REPORT_BINDING_INVALID")
    return report_digest


def classify_chat_context_shadow_eval_label(
    *,
    dlp_result: Mapping[str, Any] | None,
    explicit_business_confirmation: bool,
    manager_or_admin_approved: bool,
    pii_zero: bool,
    false_learning_zero: bool,
) -> str:
    if not isinstance(dlp_result, Mapping):
        return "DROP"
    if (
        dlp_result.get("passed") is not True
        or dlp_result.get("pii_detected") is not False
        or dlp_result.get("secret_detected") is not False
        or dlp_result.get("policy_violation") is not False
    ):
        return "BLOCK"
    if pii_zero is not True or false_learning_zero is not True:
        return "DROP"
    if explicit_business_confirmation is not True:
        return "EXCLUDE"
    if manager_or_admin_approved is not True:
        return "DROP"
    return "LEARN"


def _checked_required_bool(data: Mapping[str, Any], field_name: str, drop_reason: str) -> bool:
    value = bool_field(data, field_name, default=False, error_code=drop_reason)
    if value is not True:
        _fail(drop_reason)
    return value


def _checked_source_refs(data: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    try:
        return source_refs_from_mapping(data)
    except ProducerInputError:
        _fail("SOURCE_REF_INVALID")


def _normalize_chat_source_refs(
    source_refs: Sequence[Mapping[str, str]] | None,
    *,
    fallback_digest: str,
) -> tuple[dict[str, str], ...]:
    if not source_refs:
        _fail("SOURCE_REF_INVALID")
    try:
        refs = normalize_source_refs(
            source_refs,
            fallback_type="usage_log",
            fallback_digest=fallback_digest,
        )
    except ProducerInputError:
        _fail("SOURCE_REF_INVALID")
    for ref in refs:
        if ref["ref_type"] not in ALLOWED_CHAT_SOURCE_REF_TYPES:
            _fail("SOURCE_REF_INVALID")
    if not any(ref["ref_type"] == "usage_log" for ref in refs):
        _fail("SOURCE_REF_INVALID")
    return refs


def coerce_chat_context_artifact(
    artifact: ChatContextLearningArtifact | Mapping[str, Any],
    *,
    run_mode: str | None = "production",
) -> ChatContextLearningArtifact:
    normalized_run_mode = _normalize_run_mode(run_mode)
    data = artifact_to_mapping(artifact, ChatContextLearningArtifact)
    _reject_runtime_mode_keys(data)
    try:
        ensure_no_forbidden_keys(data)
        ensure_exact_fields(data, ChatContextLearningArtifact)
    except ProducerInputError:
        _fail("SCHEMA_KEYS_INVALID")
    context_digest = str_field(data, "context_digest", "CONTEXT_DIGEST_INVALID")
    evidence_digest = _require_evidence_digest(data["evidence_digest"] if "evidence_digest" in data else None, context_digest=context_digest)
    return ChatContextLearningArtifact(
        explicit_business_confirmation=_checked_required_bool(
            data,
            "explicit_business_confirmation",
            "BUSINESS_CONFIRMATION_REQUIRED",
        ),
        manager_or_admin_approved=_checked_required_bool(
            data,
            "manager_or_admin_approved",
            "MANAGER_APPROVAL_REQUIRED",
        ),
        shadow_eval_cases=int_field(data, "shadow_eval_cases", "SCHEMA_KEYS_INVALID"),
        pii_zero=_checked_required_bool(data, "pii_zero", "PII_NOT_ZERO"),
        false_learning_zero=_checked_required_bool(
            data,
            "false_learning_zero",
            "FALSE_LEARNING_NOT_ZERO",
        ),
        context_digest=context_digest,
        expected_effect_digest=str_field(data, "expected_effect_digest", "SCHEMA_KEYS_INVALID"),
        verified_by=validate_verified_by(data["verified_by"] if "verified_by" in data else None),
        verified_at=validate_verified_at(data["verified_at"] if "verified_at" in data else None),
        evidence_ref=validate_evidence_ref(
            data["evidence_ref"] if "evidence_ref" in data else None,
            run_mode=normalized_run_mode,
        ),
        evidence_digest=evidence_digest,
        source_refs=_checked_source_refs(data),
        evidence_report_sha256=_validate_evidence_report_binding(
            data["evidence_report_sha256"] if "evidence_report_sha256" in data else None,
            evidence_digest=evidence_digest,
            run_mode=normalized_run_mode,
        ),
    )


def build_chat_context_candidate(
    artifact: ChatContextLearningArtifact | Mapping[str, Any],
    *,
    run_mode: str | None = "production",
) -> dict[str, Any]:
    item = coerce_chat_context_artifact(artifact, run_mode=run_mode)
    if item.shadow_eval_cases < 100:
        _fail("SHADOW_EVAL_CASES_TOO_LOW")
    context_digest = validate_digest_or_drop(item.context_digest, "CONTEXT")
    validate_digest_or_drop(item.expected_effect_digest, "EVIDENCE")
    evidence_digest = _require_evidence_digest(item.evidence_digest, context_digest=context_digest)
    source_refs = _normalize_chat_source_refs(
        item.source_refs,
        fallback_digest=context_digest,
    )
    payload = {
        "explicit_business_confirmation": item.explicit_business_confirmation,
        "manager_or_admin_approved": item.manager_or_admin_approved,
        "shadow_eval_cases": item.shadow_eval_cases,
        "pii_zero": item.pii_zero,
        "false_learning_zero": item.false_learning_zero,
        "context_digest": context_digest,
    }
    if set(payload) != PAYLOAD_KEYS:
        _fail("SCHEMA_KEYS_INVALID")
    candidate = build_candidate_envelope(
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
    if item.evidence_report_sha256 is not None:
        candidate["verification"]["evidence_report_sha256"] = item.evidence_report_sha256
        ensure_no_forbidden_keys(candidate)
    return candidate


def _normalize_drop_reason(reason: str | None) -> str | None:
    mapping = {
        "CHAT_LEARNING_DISABLED": "CHAT_CONTEXT_DISABLED",
        "CHAT_BUSINESS_CONFIRMATION_REQUIRED": "BUSINESS_CONFIRMATION_REQUIRED",
        "CHAT_MANAGER_APPROVAL_REQUIRED": "MANAGER_APPROVAL_REQUIRED",
        "CHAT_SHADOW_EVAL_CASES_INVALID": "SCHEMA_KEYS_INVALID",
        "CHAT_SHADOW_EVAL_INSUFFICIENT": "SHADOW_EVAL_CASES_TOO_LOW",
        "CHAT_SHADOW_EVAL_FAILED": "FALSE_LEARNING_NOT_ZERO",
        "CHAT_CONTEXT_DIGEST_INVALID": "CONTEXT_DIGEST_INVALID",
        "SOURCE_REF_TYPE_INVALID": "SOURCE_REF_INVALID",
        "SOURCE_REF_DIGEST_INVALID": "SOURCE_REF_INVALID",
        "SOURCE_REFS_NOT_SEQUENCE": "SOURCE_REF_INVALID",
        "SOURCE_REF_NOT_OBJECT": "SOURCE_REF_INVALID",
        "EVIDENCE_DIGEST_REQUIRED": "EVIDENCE_DIGEST_INVALID",
        "EXPECTED_EFFECT_DIGEST_REQUIRED": "EVIDENCE_DIGEST_INVALID",
        "EXPECTED_EFFECT_DIGEST_INVALID": "EVIDENCE_DIGEST_INVALID",
    }
    normalized = mapping.get(reason, reason)
    if normalized is not None and normalized not in ALLOWED_DROP_REASONS:
        return "SCHEMA_KEYS_INVALID"
    return normalized


def ingest_verified_chat_context(
    artifact: ChatContextLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
    *,
    run_mode: str | None = "production",
) -> dict[str, Any]:
    try:
        candidate = build_chat_context_candidate(artifact, run_mode=run_mode)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, ChatContextProducerError(_normalize_drop_reason(str(exc)) or "SCHEMA_KEYS_INVALID"))
    result = ingest_candidate(candidate, runner)
    result["drop_reason"] = _normalize_drop_reason(result.get("drop_reason"))
    return result
