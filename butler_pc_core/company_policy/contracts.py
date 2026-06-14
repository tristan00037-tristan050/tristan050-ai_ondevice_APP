from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VAULT_REF_RE = re.compile(r"^local-vault://[A-Za-z0-9_.:/-]+$")
ROLE_VALUES = {"employee", "manager", "admin"}
DOC_GRADE_VALUES = {"restricted", "confidential", "internal", "public"}
POLICY_STATUS_VALUES = {"DRAFT", "ACTIVE", "DEPRECATED"}
DECISION_VALUES = {"allow", "needs_review", "block"}
FORMAT_KIND_VALUES = {
    "report",
    "proposal",
    "official_letter",
    "summary",
    "contract_review",
    "meeting_agenda",
    "freeform",
    "cash_flow_daily",
    "cash_flow_weekly",
    "cash_flow_monthly",
    "voucher",
    "financial_statement",
    "pnl_summary",
}
FORMAT_STATUS_VALUES = {"DRAFT", "ACTIVE", "DEPRECATED"}
RAW_FORBIDDEN_KEYS = {
    "raw",
    "raw" + "_text",
    "raw_policy",
    "raw_template",
    "template_text",
    "content",
    "file_path",
    "absolute_path",
    "token",
    "password",
    "secret",
    "email",
}


class ContractValidationError(ValueError):
    """Raised when a CompanyPolicy/Format/Gate contract is invalid."""


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_json_digest(value: Any) -> str:
    return sha256_text(stable_json(value))


def require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise ContractValidationError(f"{field_name}_DIGEST_INVALID")
    return value


def _assert_no_unknown_keys(data: dict[str, Any], allowed: set[str], object_name: str) -> None:
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        raise ContractValidationError(f"{object_name}_UNKNOWN_FIELD_{unknown[0]}")


def _assert_no_raw_keys(data: Any, path: str = "$") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            lowered = str(key).lower()
            if lowered in RAW_FORBIDDEN_KEYS:
                raise ContractValidationError(f"RAW_FIELD_FORBIDDEN_{path}.{key}")
            _assert_no_raw_keys(value, f"{path}.{key}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _assert_no_raw_keys(item, f"{path}[{idx}]")


@dataclass(frozen=True)
class AdminContext:
    """Admin authorization context.

    Capability token proves local sidecar communication only. This object proves
    admin RBAC. Never store token, name, email, or raw admin identifier.
    """

    admin_id_digest: str
    role: Literal["admin", "manager", "employee"]
    admin_session_digest: str
    auth_method: Literal["os_keychain", "tauri_secure_invoke", "test_only"]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        require_digest(data["admin_id_digest"], "admin_id")
        require_digest(data["admin_session_digest"], "admin_session")
        if data["role"] not in ROLE_VALUES:
            raise ContractValidationError("ADMIN_ROLE_INVALID")
        if data["auth_method"] not in {"os_keychain", "tauri_secure_invoke", "test_only"}:
            raise ContractValidationError("ADMIN_AUTH_METHOD_INVALID")
        return data


@dataclass(frozen=True)
class AccessRule:
    dept_digest: str
    role: Literal["employee", "manager", "admin"]
    doc_grade: Literal["restricted", "confidential", "internal", "public"]
    decision: Literal["allow", "needs_review", "block"]
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        require_digest(data["dept_digest"], "dept")
        if data["role"] not in ROLE_VALUES:
            raise ContractValidationError("ACCESS_RULE_ROLE_INVALID")
        if data["doc_grade"] not in DOC_GRADE_VALUES:
            raise ContractValidationError("ACCESS_RULE_DOC_GRADE_INVALID")
        if data["decision"] not in DECISION_VALUES:
            raise ContractValidationError("ACCESS_RULE_DECISION_INVALID")
        if not re.match(r"^[A-Z][A-Z0-9_]{0,63}$", data["reason_code"]):
            raise ContractValidationError("ACCESS_RULE_REASON_CODE_INVALID")
        return data


@dataclass(frozen=True)
class CompanyPolicy:
    schema_version: Literal["company_policy.v1"]
    policy_id: str
    version: int
    status: Literal["DRAFT", "ACTIVE", "DEPRECATED"]
    default_action: Literal["block"]
    doc_grades: list[Literal["restricted", "confidential", "internal", "public"]]
    access_rules: list[AccessRule]
    external_send_rules: dict[str, Literal["allow", "needs_review", "block"]]
    masking_engine_verified: bool
    effective_from: str
    expires_at: str | None
    registered_by_digest: str
    previous_policy_digest: str | None
    policy_digest: str

    def unsigned_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["access_rules"] = [rule.to_dict() for rule in self.access_rules]
        data.pop("policy_digest", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data["policy_digest"] = self.policy_digest
        validate_company_policy_dict(data)
        expected = compute_policy_digest(data)
        if data["policy_digest"] != expected:
            raise ContractValidationError("POLICY_DIGEST_MISMATCH")
        return data


@dataclass(frozen=True)
class CompanyFormat:
    schema_version: Literal["company_format.v1"]
    format_id: str
    format_kind: str
    status: Literal["DRAFT", "ACTIVE", "DEPRECATED"]
    template_ref: str
    template_digest: str
    metadata: dict[str, Any]
    registered_by_digest: str
    registered_at: str
    previous_format_digest: str | None
    format_digest: str

    def unsigned_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data.pop("format_digest", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data["format_digest"] = self.format_digest
        validate_company_format_dict(data)
        expected = compute_format_digest(data)
        if data["format_digest"] != expected:
            raise ContractValidationError("FORMAT_DIGEST_MISMATCH")
        return data


@dataclass(frozen=True)
class PolicyTaskEnvelope:
    schema_version: Literal["policy_task_envelope.v1"]
    request_id: str
    tenant_digest: str
    dept_digest: str
    user_role: Literal["employee", "manager", "admin"]
    target_box_id: str
    operation: str
    doc_grade: Literal["restricted", "confidential", "internal", "public"]
    external_send_requested: bool
    format_id: str | None
    learning_allowed: bool
    retention_days: int
    masking_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_policy_task_envelope_dict(data)
        return data


@dataclass(frozen=True)
class PolicyGateResult:
    schema_version: Literal["policy_gate_result.v1"]
    allowed: bool
    decision: Literal["allow", "needs_review", "block"]
    block_reason: str | None
    applied_policy_digest: str | None
    audit_ref: str
    external_send_zero: Literal[True]
    raw_text_logged: Literal[False]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_policy_gate_result_dict(data)
        return data


def compute_policy_digest(policy_dict: dict[str, Any]) -> str:
    payload = copy.deepcopy(policy_dict)
    payload.pop("policy_digest", None)
    return stable_json_digest(payload)


def compute_format_digest(format_dict: dict[str, Any]) -> str:
    payload = copy.deepcopy(format_dict)
    payload.pop("format_digest", None)
    return stable_json_digest(payload)


def make_company_policy(
    *,
    registered_by_digest: str,
    access_rules: list[AccessRule],
    status: str = "ACTIVE",
    policy_id: str | None = None,
    version: int = 1,
    masking_engine_verified: bool = False,
    previous_policy_digest: str | None = None,
    effective_from: str | None = None,
    expires_at: str | None = None,
    external_send_rules: dict[str, str] | None = None,
) -> CompanyPolicy:
    data = {
        "schema_version": "company_policy.v1",
        "policy_id": policy_id or "policy-" + uuid.uuid4().hex,
        "version": version,
        "status": status,
        "default_action": "block",
        "doc_grades": ["restricted", "confidential", "internal", "public"],
        "access_rules": [rule.to_dict() for rule in access_rules],
        "external_send_rules": external_send_rules or {
            "restricted": "block",
            "confidential": "block",
            "internal": "needs_review",
            "public": "allow",
        },
        "masking_engine_verified": masking_engine_verified,
        "effective_from": effective_from or now_utc(),
        "expires_at": expires_at,
        "registered_by_digest": registered_by_digest,
        "previous_policy_digest": previous_policy_digest,
        "policy_digest": "",
    }
    data["policy_digest"] = compute_policy_digest(data)
    validate_company_policy_dict(data)
    return CompanyPolicy(
        schema_version="company_policy.v1",
        policy_id=data["policy_id"],
        version=data["version"],
        status=data["status"],
        default_action="block",
        doc_grades=data["doc_grades"],
        access_rules=access_rules,
        external_send_rules=data["external_send_rules"],
        masking_engine_verified=masking_engine_verified,
        effective_from=data["effective_from"],
        expires_at=expires_at,
        registered_by_digest=registered_by_digest,
        previous_policy_digest=previous_policy_digest,
        policy_digest=data["policy_digest"],
    )


def make_company_format(
    *,
    format_kind: str,
    template_ref: str,
    template_digest: str,
    metadata: dict[str, Any],
    registered_by_digest: str,
    status: str = "ACTIVE",
    format_id: str | None = None,
    previous_format_digest: str | None = None,
    registered_at: str | None = None,
) -> CompanyFormat:
    data = {
        "schema_version": "company_format.v1",
        "format_id": format_id or "format-" + uuid.uuid4().hex,
        "format_kind": format_kind,
        "status": status,
        "template_ref": template_ref,
        "template_digest": template_digest,
        "metadata": metadata,
        "registered_by_digest": registered_by_digest,
        "registered_at": registered_at or now_utc(),
        "previous_format_digest": previous_format_digest,
        "format_digest": "",
    }
    data["format_digest"] = compute_format_digest(data)
    validate_company_format_dict(data)
    return CompanyFormat(
        schema_version="company_format.v1",
        format_id=data["format_id"],
        format_kind=format_kind,
        status=status,
        template_ref=template_ref,
        template_digest=template_digest,
        metadata=metadata,
        registered_by_digest=registered_by_digest,
        registered_at=data["registered_at"],
        previous_format_digest=previous_format_digest,
        format_digest=data["format_digest"],
    )


def validate_company_policy_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "policy_id", "version", "status", "default_action", "doc_grades",
        "access_rules", "external_send_rules", "masking_engine_verified", "effective_from",
        "expires_at", "registered_by_digest", "previous_policy_digest", "policy_digest",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("COMPANY_POLICY_NOT_OBJECT")
    _assert_no_unknown_keys(data, allowed, "COMPANY_POLICY")
    _assert_no_raw_keys(data)
    required = allowed
    missing = sorted(required - set(data))
    if missing:
        raise ContractValidationError(f"COMPANY_POLICY_MISSING_{missing[0]}")
    if data["schema_version"] != "company_policy.v1":
        raise ContractValidationError("COMPANY_POLICY_SCHEMA_VERSION_INVALID")
    if data["status"] not in POLICY_STATUS_VALUES:
        raise ContractValidationError("COMPANY_POLICY_STATUS_INVALID")
    if data["default_action"] != "block":
        raise ContractValidationError("COMPANY_POLICY_DEFAULT_ACTION_MUST_BLOCK")
    if not isinstance(data["version"], int) or data["version"] < 1:
        raise ContractValidationError("COMPANY_POLICY_VERSION_INVALID")
    if not isinstance(data["doc_grades"], list) or set(data["doc_grades"]) != DOC_GRADE_VALUES:
        raise ContractValidationError("COMPANY_POLICY_DOC_GRADES_INVALID")
    if not isinstance(data["access_rules"], list):
        raise ContractValidationError("COMPANY_POLICY_ACCESS_RULES_INVALID")
    for rule in data["access_rules"]:
        _assert_no_unknown_keys(rule, {"dept_digest", "role", "doc_grade", "decision", "reason_code"}, "ACCESS_RULE")
        AccessRule(**rule).to_dict()
    rules = data["external_send_rules"]
    if not isinstance(rules, dict) or set(rules) != DOC_GRADE_VALUES:
        raise ContractValidationError("COMPANY_POLICY_EXTERNAL_RULES_INVALID")
    for grade, decision in rules.items():
        if decision not in DECISION_VALUES:
            raise ContractValidationError("COMPANY_POLICY_EXTERNAL_RULE_DECISION_INVALID")
    if not isinstance(data["masking_engine_verified"], bool):
        raise ContractValidationError("COMPANY_POLICY_MASKING_FLAG_INVALID")
    require_digest(data["registered_by_digest"], "registered_by")
    if data["previous_policy_digest"] is not None:
        require_digest(data["previous_policy_digest"], "previous_policy")
    require_digest(data["policy_digest"], "policy")
    return data


def validate_company_format_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "format_id", "format_kind", "status", "template_ref",
        "template_digest", "metadata", "registered_by_digest", "registered_at",
        "previous_format_digest", "format_digest",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("COMPANY_FORMAT_NOT_OBJECT")
    _assert_no_unknown_keys(data, allowed, "COMPANY_FORMAT")
    _assert_no_raw_keys(data)
    missing = sorted(allowed - set(data))
    if missing:
        raise ContractValidationError(f"COMPANY_FORMAT_MISSING_{missing[0]}")
    if data["schema_version"] != "company_format.v1":
        raise ContractValidationError("COMPANY_FORMAT_SCHEMA_VERSION_INVALID")
    if data["format_kind"] not in FORMAT_KIND_VALUES:
        raise ContractValidationError("COMPANY_FORMAT_KIND_INVALID")
    if data["status"] not in FORMAT_STATUS_VALUES:
        raise ContractValidationError("COMPANY_FORMAT_STATUS_INVALID")
    if not isinstance(data["template_ref"], str) or not VAULT_REF_RE.match(data["template_ref"]):
        raise ContractValidationError("COMPANY_FORMAT_TEMPLATE_REF_INVALID")
    require_digest(data["template_digest"], "template")
    require_digest(data["registered_by_digest"], "registered_by")
    if data["previous_format_digest"] is not None:
        require_digest(data["previous_format_digest"], "previous_format")
    require_digest(data["format_digest"], "format")
    metadata = data["metadata"]
    if not isinstance(metadata, dict):
        raise ContractValidationError("COMPANY_FORMAT_METADATA_INVALID")
    _assert_no_unknown_keys(metadata, {"title_digest", "language", "dept_digest"}, "FORMAT_METADATA")
    require_digest(metadata["title_digest"], "title")
    require_digest(metadata["dept_digest"], "dept")
    if not isinstance(metadata["language"], str) or not metadata["language"]:
        raise ContractValidationError("FORMAT_METADATA_LANGUAGE_INVALID")
    return data


def validate_policy_task_envelope_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "request_id", "tenant_digest", "dept_digest", "user_role",
        "target_box_id", "operation", "doc_grade", "external_send_requested", "format_id",
        "learning_allowed", "retention_days", "masking_requested",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("POLICY_TASK_ENVELOPE_NOT_OBJECT")
    _assert_no_unknown_keys(data, allowed, "POLICY_TASK_ENVELOPE")
    _assert_no_raw_keys(data)
    missing = sorted(allowed - set(data))
    if missing:
        raise ContractValidationError(f"POLICY_TASK_ENVELOPE_MISSING_{missing[0]}")
    if data["schema_version"] != "policy_task_envelope.v1":
        raise ContractValidationError("POLICY_TASK_ENVELOPE_SCHEMA_VERSION_INVALID")
    require_digest(data["tenant_digest"], "tenant")
    require_digest(data["dept_digest"], "dept")
    if data["user_role"] not in ROLE_VALUES:
        raise ContractValidationError("POLICY_TASK_USER_ROLE_INVALID")
    if data["doc_grade"] not in DOC_GRADE_VALUES:
        raise ContractValidationError("POLICY_DOC_GRADE_UNKNOWN")
    if not isinstance(data["external_send_requested"], bool):
        raise ContractValidationError("POLICY_EXTERNAL_SEND_FLAG_INVALID")
    if not isinstance(data["learning_allowed"], bool):
        raise ContractValidationError("POLICY_LEARNING_ALLOWED_FLAG_INVALID")
    if not isinstance(data["masking_requested"], bool):
        raise ContractValidationError("POLICY_MASKING_FLAG_INVALID")
    if not isinstance(data["retention_days"], int) or data["retention_days"] < 0:
        raise ContractValidationError("POLICY_RETENTION_DAYS_INVALID")
    return data


def validate_policy_gate_result_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "allowed", "decision", "block_reason", "applied_policy_digest",
        "audit_ref", "external_send_zero", "raw_text_logged",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("POLICY_GATE_RESULT_NOT_OBJECT")
    _assert_no_unknown_keys(data, allowed, "POLICY_GATE_RESULT")
    _assert_no_raw_keys({k: v for k, v in data.items() if k != "raw_text_logged"})
    missing = sorted(allowed - set(data))
    if missing:
        raise ContractValidationError(f"POLICY_GATE_RESULT_MISSING_{missing[0]}")
    if data["schema_version"] != "policy_gate_result.v1":
        raise ContractValidationError("POLICY_GATE_RESULT_SCHEMA_VERSION_INVALID")
    if data["decision"] not in DECISION_VALUES:
        raise ContractValidationError("POLICY_GATE_DECISION_INVALID")
    if data["allowed"] != (data["decision"] == "allow"):
        raise ContractValidationError("POLICY_GATE_ALLOWED_DECISION_MISMATCH")
    if data["applied_policy_digest"] is not None:
        require_digest(data["applied_policy_digest"], "applied_policy")
    require_digest(data["audit_ref"], "audit_ref")
    if data["external_send_zero"] is not True:
        raise ContractValidationError("POLICY_GATE_EXTERNAL_SEND_ZERO_REQUIRED")
    if data["raw_text_logged"] is not False:
        raise ContractValidationError("POLICY_GATE_RAW_TEXT_LOGGED_MUST_FALSE")
    return data
