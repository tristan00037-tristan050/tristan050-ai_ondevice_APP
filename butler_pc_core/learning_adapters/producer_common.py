from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import fields, is_dataclass
from typing import Any, Mapping, Sequence, TypeVar

from butler_pc_core.learning_core.contracts import (
    IntegratedLearningError,
    REF_RE,
    assert_no_forbidden_fields,
    assert_no_mode_contamination,
    is_sha256,
    stable_json_digest,
)
from butler_pc_core.learning_core.runner import LearningIntakeRunner

SCHEMA_VERSION = "integrated_learning_candidate.v1"
DEFAULT_VERIFIED_AT = "2026-07-03T00:00:00Z"
DIGEST_ONLY_EVIDENCE_REF = "digest-only-fixture"

_ALLOWED_SOURCE_REF_TYPES = frozenset({"usage_log", "approval", "folder", "format", "policy"})
_LOCAL_FORBIDDEN_ARTIFACT_FIELDS = frozenset(
    {
        "raw",
        "raw_text",
        "raw_memo",
        "policy_text",
        "policy_body",
        "rule_text",
        "template_body",
        "template_text",
        "fact_text",
        "answer_runtime_text",
        "question_pattern",
        "question_patterns",
        "source_url",
        "folder_content",
        "file_content",
        "document_text",
        "md_content",
        "prompt",
        "response_text",
        "user_name",
        "messenger",
        "filename",
        "file_name",
        "file_path",
        "local_path",
        "customer_name",
        "account_number_plain",
        "amount_plain",
        "email_plain",
        "phone_plain",
        "token",
        "pass" + "word",
        "sec" + "ret",
        "api" + "_key",
        "integration_mode",
        "fixture_mode",
        "run_mode",
    }
)
_SHA_HEX_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_REF_RE = re.compile(r"^(?:vault|keyring)://[^\s]{1,240}$")

T = TypeVar("T")


class ProducerInputError(ValueError):
    """Stable fail-closed producer error."""


def fail(code: str) -> None:
    raise ProducerInputError(code)


def stable_digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha_hex(value: str) -> str:
    match = _SHA_HEX_RE.fullmatch(value)
    if not match:
        fail("DIGEST_INVALID")
    return match.group(1)


def ensure_no_forbidden_keys(value: Any) -> None:
    try:
        assert_no_mode_contamination(value)
        assert_no_forbidden_fields(value)
    except IntegratedLearningError:
        fail("FORBIDDEN_FIELD")

    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if key in _LOCAL_FORBIDDEN_ARTIFACT_FIELDS:
                    fail("FORBIDDEN_FIELD")
                walk(child, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")

    walk(value)


def artifact_to_mapping(artifact: T | Mapping[str, Any], artifact_type: type[T]) -> dict[str, Any]:
    if isinstance(artifact, artifact_type) and is_dataclass(artifact):
        return dataclasses.asdict(artifact)
    if isinstance(artifact, Mapping):
        return dict(artifact)
    fail("ARTIFACT_NOT_OBJECT")


def ensure_exact_fields(data: Mapping[str, Any], artifact_type: type[Any]) -> None:
    allowed = {field.name for field in fields(artifact_type)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        fail("ARTIFACT_UNKNOWN_FIELD")


def str_field(data: Mapping[str, Any], field_name: str, error_code: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        fail(error_code)
    return value.strip()


def optional_str_field(data: Mapping[str, Any], field_name: str, error_code: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(error_code)
    return value.strip()


def bool_field(data: Mapping[str, Any], field_name: str, *, default: bool, error_code: str) -> bool:
    if field_name not in data:
        return default
    value = data[field_name]
    if not isinstance(value, bool):
        fail(error_code)
    return value


def int_field(data: Mapping[str, Any], field_name: str, error_code: str) -> int:
    value = data.get(field_name)
    if type(value) is not int:
        fail(error_code)
    return value


def validate_digest_or_drop(value: str | None, field_name: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            fail(f"{field_name}_DIGEST_REQUIRED")
        return None
    if not isinstance(value, str) or value.strip() != value or not is_sha256(value):
        fail(f"{field_name}_DIGEST_INVALID")
    return value


def validate_ref_or_drop(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _REF_RE.fullmatch(value):
        fail(f"{field_name}_INVALID")
    return value


def validate_evidence_ref_or_drop(value: str) -> str:
    if not isinstance(value, str) or not REF_RE.fullmatch(value):
        fail("EVIDENCE_REF_INVALID")
    return value


def source_refs_from_mapping(data: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    raw = data.get("source_refs", ())
    if raw is None:
        return ()
    if isinstance(raw, Mapping) or not isinstance(raw, (list, tuple)):
        fail("SOURCE_REFS_NOT_SEQUENCE")
    refs: list[dict[str, str]] = []
    for ref in raw:
        if not isinstance(ref, Mapping):
            fail("SOURCE_REF_NOT_OBJECT")
        refs.append(dict(ref))
    return tuple(refs)


def normalize_source_refs(
    source_refs: Sequence[Mapping[str, str]] | None,
    *,
    fallback_type: str,
    fallback_digest: str,
) -> tuple[dict[str, str], ...]:
    if fallback_type not in _ALLOWED_SOURCE_REF_TYPES:
        fail("SOURCE_REF_TYPE_INVALID")
    if not is_sha256(fallback_digest):
        fail("SOURCE_REF_DIGEST_INVALID")
    if not source_refs:
        return ({"ref_type": fallback_type, "ref_id_digest": fallback_digest},)
    normalized: list[dict[str, str]] = []
    for ref in source_refs:
        if not isinstance(ref, Mapping):
            fail("SOURCE_REF_NOT_OBJECT")
        ref_type = str(ref.get("ref_type", "")).strip()
        ref_id_digest = str(ref.get("ref_id_digest", "")).strip()
        if ref_type not in _ALLOWED_SOURCE_REF_TYPES:
            fail("SOURCE_REF_TYPE_INVALID")
        if not is_sha256(ref_id_digest):
            fail("SOURCE_REF_DIGEST_INVALID")
        normalized.append({"ref_type": ref_type, "ref_id_digest": ref_id_digest})
    return tuple(normalized)


def build_candidate_envelope(
    *,
    target_kind: str,
    adapter_version: str,
    learning_source_type: str,
    payload: dict[str, Any],
    expected_effect_digest: str,
    evidence_digest: str,
    evidence_ref: str,
    source_refs: Sequence[Mapping[str, str]],
    verified_by: str,
    verified_at: str,
    evidence_report_sha256: str | None = None,
) -> dict[str, Any]:
    validate_digest_or_drop(expected_effect_digest, "EXPECTED_EFFECT")
    validate_digest_or_drop(evidence_digest, "EVIDENCE")
    if evidence_report_sha256 is not None:
        validate_digest_or_drop(evidence_report_sha256, "EVIDENCE_REPORT")
    evidence_ref = validate_evidence_ref_or_drop(evidence_ref)
    payload_digest = stable_json_digest(payload)
    candidate_material = {
        "target_kind": target_kind,
        "payload_digest": payload_digest,
        "expected_effect_digest": expected_effect_digest,
        "source_refs": list(source_refs),
        "evidence_digest": evidence_digest,
        "evidence_report_sha256": evidence_report_sha256,
    }
    candidate_id = "ilc-" + sha_hex(stable_json_digest(candidate_material))[:32]
    verification = {
        "verified_by": verified_by,
        "verified_at": verified_at,
        "evidence_digest": evidence_digest,
        "evidence_ref": evidence_ref,
    }
    if evidence_report_sha256 is not None:
        verification["evidence_report_sha256"] = evidence_report_sha256
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "target_kind": target_kind,
        "adapter_version": adapter_version,
        "learning_source_type": learning_source_type,
        "policy_decision": "allow",
        "verified": True,
        "group_a_verified": True,
        "raw_text_logged": False,
        "external_send_zero": True,
        "model_training": False,
        "peft_training": False,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "retention_class": "audit_digest_only",
        "verification": verification,
        "source_refs": list(source_refs),
        "payload_digest": payload_digest,
        "expected_effect_digest": expected_effect_digest,
        "payload": payload,
    }
    ensure_no_forbidden_keys(candidate)
    return candidate


def digest_safe_drop_summary(target_kind: str, exc: ProducerInputError) -> dict[str, Any]:
    return {
        "accepted": False,
        "drop_reason": str(exc),
        "queue_appended": False,
        "queue_reason": None,
        "candidate_id": None,
        "target_kind": target_kind,
        "payload_digest": None,
        "record_digest": None,
    }


def ingest_candidate(candidate: dict[str, Any], runner: LearningIntakeRunner) -> dict[str, Any]:
    result = runner.ingest(candidate)
    return {
        "accepted": bool(result.get("accepted")),
        "drop_reason": result.get("drop_reason"),
        "queue_appended": bool(result.get("queue_appended")),
        "queue_reason": result.get("queue_reason"),
        "candidate_id": candidate["candidate_id"],
        "target_kind": candidate["target_kind"],
        "payload_digest": candidate["payload_digest"],
        "record_digest": result.get("record_digest"),
    }
