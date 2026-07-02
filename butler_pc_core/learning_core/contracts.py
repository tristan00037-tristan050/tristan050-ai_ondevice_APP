from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

SCHEMA_VERSION = "integrated_learning_candidate.v1"
RETENTION_CLASS = "audit_digest_only"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REF_RE = re.compile(
    r"^(?:digest-only-fixture|sha256:[0-9a-f]{64}|"
    r"vault://butler/evidence/[A-Za-z0-9_-]{1,128}|"
    r"keyring://butler/evidence/[A-Za-z0-9_-]{1,128})$"
)
RFC3339_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CANDIDATE_ID_RE = re.compile(r"^ilc-[0-9a-f]{16,64}$")
EVIDENCE_REF_DENY_RE = re.compile(
    r"https?://|file://|s3://|gs://|/Users/|/home/|[A-Za-z]:\\|\\\\|\.\.|~|@|\s"
)

TARGET_KINDS = frozenset(
    {
        "box_rule_patch",
        "policy_rule",
        "company_format",
        "approved_fact",
        "folder_doc",
        "chat_context",
    }
)

EXPECTED_SOURCE_TYPE = {
    "box_rule_patch": "verified_box_rule_patch",
    "policy_rule": "verified_policy_rule",
    "company_format": "verified_company_format",
    "approved_fact": "verified_approved_fact",
    "folder_doc": "verified_folder_doc",
    "chat_context": "verified_chat_context",
}

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "raw",
        "raw_text",
        "raw_memo",
        "filename",
        "file_name",
        "file_path",
        "md_content",
        "transaction_text",
        "prompt",
        "prompt_text",
        "response_text",
        "speaker",
        "employee_name",
        "timestamp_raw",
        "path",
        "url",
        "message_id",
        "customer_name",
        "account_number_plain",
        "amount_plain",
        "email_plain",
        "phone_plain",
        "local_path",
        "token",
        "password",
        "secret",
        "api_key",
        # Explicitly banned to prevent real/contract_only spoofing in the new path.
        "integration_mode",
    }
)

ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "target_kind",
        "adapter_version",
        "learning_source_type",
        "policy_decision",
        "verified",
        "group_a_verified",
        "raw_text_logged",
        "external_send_zero",
        "model_training",
        "peft_training",
        "human_review_required",
        "auto_apply_to_runtime",
        "retention_class",
        "verification",
        "source_refs",
        "payload_digest",
        "expected_effect_digest",
        "payload",
    }
)

ALLOWED_VERIFICATION_FIELDS = frozenset(
    {"verified_by", "verified_at", "evidence_digest", "evidence_ref"}
)
ALLOWED_VERIFIED_BY = frozenset(
    {"group_a", "integrated_learning_verifier", "privacy_officer", "security_reviewer"}
)
ALLOWED_SOURCE_REF_FIELDS = frozenset({"ref_type", "ref_id_digest"})
ALLOWED_SOURCE_REF_TYPES = frozenset({"usage_log", "approval", "folder", "format", "policy"})


class IntegratedLearningError(ValueError):
    """Raised only for programmer misuse. Runtime gate returns GateResult."""


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    candidate: dict[str, Any] | None = None
    drop_reason: str | None = None

    @classmethod
    def accept(cls, candidate: dict[str, Any]) -> "GateResult":
        return cls(True, copy.deepcopy(candidate), None)

    @classmethod
    def drop(cls, reason: str) -> "GateResult":
        return cls(False, None, reason)


class LearningAdapter(Protocol):
    target_kind: str

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        ...


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_digest(value: Any) -> str:
    return sha256_text(stable_json(value))


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def assert_no_forbidden_fields(value: Any, *, path: str = "$", allow_payload_keys: bool = False) -> None:
    """Fail on banned field names anywhere in candidates, queues, manifests, or evidence.

    The field `raw_text_logged` is intentionally allowed; `raw_text` is not.
    Adapter payload keys are still scanned by default because adapter schemas must
    also be digest/ref-only.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_FIELD_NAMES:
                raise IntegratedLearningError(f"FORBIDDEN_FIELD:{path}.{key}")
            assert_no_forbidden_fields(child, path=f"{path}.{key}", allow_payload_keys=allow_payload_keys)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_forbidden_fields(child, path=f"{path}[{index}]", allow_payload_keys=allow_payload_keys)


def _validate_exact_fields(data: dict[str, Any], allowed: frozenset[str], code: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise IntegratedLearningError(f"{code}:{unknown[0]}")


def _require_plain_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise IntegratedLearningError(code)
    if value.strip() != value:
        raise IntegratedLearningError(code)
    if any(ord(ch) < 32 for ch in value):
        raise IntegratedLearningError(code)
    return value


def validate_verified_by(value: Any) -> str:
    verified_by = _require_plain_string(value, "VERIFIED_BY_INVALID")
    if verified_by not in ALLOWED_VERIFIED_BY:
        raise IntegratedLearningError("VERIFIED_BY_INVALID")
    return verified_by


def validate_verified_at(value: Any) -> str:
    verified_at = _require_plain_string(value, "VERIFIED_AT_INVALID")
    if not RFC3339_Z_RE.fullmatch(verified_at):
        raise IntegratedLearningError("VERIFIED_AT_INVALID")
    try:
        datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise IntegratedLearningError("VERIFIED_AT_INVALID") from exc
    return verified_at


def validate_evidence_ref(value: Any) -> str:
    evidence_ref = _require_plain_string(value, "EVIDENCE_REF_INVALID")
    if EVIDENCE_REF_DENY_RE.search(evidence_ref):
        raise IntegratedLearningError("EVIDENCE_REF_INVALID")
    if not REF_RE.fullmatch(evidence_ref):
        raise IntegratedLearningError("EVIDENCE_REF_INVALID")
    return evidence_ref


def _validate_verification(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != ALLOWED_VERIFICATION_FIELDS:
        raise IntegratedLearningError("SCHEMA_KEYS_INVALID")
    validate_verified_by(value.get("verified_by"))
    validate_verified_at(value.get("verified_at"))
    if not is_sha256(value.get("evidence_digest")):
        raise IntegratedLearningError("EVIDENCE_DIGEST_INVALID")
    validate_evidence_ref(value.get("evidence_ref"))


def _validate_source_refs(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise IntegratedLearningError("SOURCE_REF_INVALID")
    if len(value) > 64:
        raise IntegratedLearningError("SOURCE_REF_INVALID")
    for item in value:
        if not isinstance(item, dict) or set(item) != ALLOWED_SOURCE_REF_FIELDS:
            raise IntegratedLearningError("SOURCE_REF_INVALID")
        if item.get("ref_type") not in ALLOWED_SOURCE_REF_TYPES:
            raise IntegratedLearningError("SOURCE_REF_INVALID")
        if not is_sha256(item.get("ref_id_digest")):
            raise IntegratedLearningError("SOURCE_REF_INVALID")


def validate_candidate_contract(candidate: dict[str, Any]) -> None:
    if not isinstance(candidate, dict):
        raise IntegratedLearningError("CANDIDATE_NOT_OBJECT")
    assert_no_forbidden_fields(candidate)
    _validate_exact_fields(candidate, ALLOWED_TOP_LEVEL_FIELDS, "CANDIDATE_UNKNOWN_FIELD")

    if candidate.get("schema_version") != SCHEMA_VERSION:
        raise IntegratedLearningError("SCHEMA_VERSION_INVALID")
    if not isinstance(candidate.get("candidate_id"), str) or not CANDIDATE_ID_RE.fullmatch(candidate["candidate_id"]):
        raise IntegratedLearningError("CANDIDATE_ID_INVALID")
    target_kind = candidate.get("target_kind")
    if target_kind not in TARGET_KINDS:
        raise IntegratedLearningError("TARGET_KIND_INVALID")
    if candidate.get("learning_source_type") != EXPECTED_SOURCE_TYPE[target_kind]:
        raise IntegratedLearningError("LEARNING_SOURCE_TYPE_INVALID")
    if not isinstance(candidate.get("adapter_version"), str) or not candidate["adapter_version"].strip():
        raise IntegratedLearningError("ADAPTER_VERSION_INVALID")

    required_literals = {
        "policy_decision": "allow",
        "verified": True,
        "group_a_verified": True,
        "raw_text_logged": False,
        "external_send_zero": True,
        "model_training": False,
        "peft_training": False,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "retention_class": RETENTION_CLASS,
    }
    for key, expected in required_literals.items():
        actual = candidate.get(key)
        if isinstance(expected, bool):
            if actual is not expected:
                raise IntegratedLearningError(f"{key.upper()}_INVALID")
        elif actual != expected:
            raise IntegratedLearningError(f"{key.upper()}_INVALID")

    _validate_verification(candidate.get("verification"))
    _validate_source_refs(candidate.get("source_refs"))
    if not is_sha256(candidate.get("payload_digest")):
        raise IntegratedLearningError("PAYLOAD_DIGEST_INVALID")
    if not is_sha256(candidate.get("expected_effect_digest")):
        raise IntegratedLearningError("EXPECTED_EFFECT_DIGEST_INVALID")
    if not isinstance(candidate.get("payload"), dict):
        raise IntegratedLearningError("PAYLOAD_NOT_OBJECT")
    # The candidate declares payload_digest. Enforce it so adapters do not verify
    # a payload different from what the envelope says was reviewed.
    if candidate["payload_digest"] != stable_json_digest(candidate["payload"]):
        raise IntegratedLearningError("PAYLOAD_DIGEST_MISMATCH")
