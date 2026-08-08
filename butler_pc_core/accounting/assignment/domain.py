"""Strict domain contracts for Box5 user assignment and learned suggestions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_SAFE_INTEGER = 9_007_199_254_740_991


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def opaque_id() -> str:
    # Assignment/rule/receipt contracts use one opaque UUID representation.
    return str(__import__("uuid").uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AssignmentScope(StrEnum):
    THIS_ONLY = "THIS_ONLY"
    SAME_VENDOR_FUTURE = "SAME_VENDOR_FUTURE"


class ConflictDecision(StrEnum):
    KEEP_EXISTING = "KEEP_EXISTING"
    REPLACE_WITH_NEW = "REPLACE_WITH_NEW"


class ReviewState(StrEnum):
    SOURCE_DECLARED_VALID = "SOURCE_DECLARED_VALID"
    AUTO_PROPOSE = "AUTO_PROPOSE"
    USER_RULE_SUGGESTED = "USER_RULE_SUGGESTED"
    USER_RULE_APPLIED_DRAFT = "USER_RULE_APPLIED_DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    # ★ RI-P0-010: invalid/missing/out-of-range 날짜·금액은 1970 대체 없이 격리한다.
    REVIEW_QUARANTINE = "REVIEW_QUARANTINE"
    NON_EXPENSE_BANK_EVENT = "NON_EXPENSE_BANK_EVENT"
    USER_ASSIGNED = "USER_ASSIGNED"


class RuleState(StrEnum):
    # Legacy value is retained only so forward migration can identify it.  It
    # is never returned by an active-rule lookup after schema v3.
    ACTIVE_SUGGESTION = "ACTIVE_SUGGESTION"
    ACTIVE_USER_RULE = "ACTIVE_USER_RULE"
    INACTIVE_USER = "INACTIVE_USER"
    INACTIVE_REGISTRY = "INACTIVE_REGISTRY"
    DEGRADED_KEY_ROTATION = "DEGRADED_KEY_ROTATION"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"


class EventType(StrEnum):
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_SUPERSEDED = "ASSIGNMENT_SUPERSEDED"
    RULE_CREATED = "RULE_CREATED"
    RULE_SUGGESTED = "RULE_SUGGESTED"
    RULE_DEACTIVATED = "RULE_DEACTIVATED"
    RULE_CONFLICT_DETECTED = "RULE_CONFLICT_DETECTED"
    RULE_CONFLICT_RESOLVED = "RULE_CONFLICT_RESOLVED"
    REGISTRY_INVALIDATED = "REGISTRY_INVALIDATED"
    RULE_APPLIED_DRAFT = "RULE_APPLIED_DRAFT"
    RULE_APPLICATION_REVERTED = "RULE_APPLICATION_REVERTED"
    QUARANTINE_CORRECTION_REQUESTED = "QUARANTINE_CORRECTION_REQUESTED"


class AssignmentError(RuntimeError):
    """Safe application error that maps directly to RFC 9457."""

    def __init__(
        self,
        code: str,
        status: int,
        safe_detail: str,
        *,
        actions: tuple[str, ...] = (),
        current_version: int | None = None,
        conflict_id: str | None = None,
        conflict_version: int | None = None,
        existing_account_id: str | None = None,
        proposed_account_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.safe_detail = safe_detail[:300]
        self.actions = actions[:5]
        self.current_version = current_version
        self.conflict_id = conflict_id
        self.conflict_version = conflict_version
        self.existing_account_id = existing_account_id
        self.proposed_account_id = proposed_account_id

    def problem(self, request_id: str) -> dict[str, Any]:
        problem = {
            "type": f"https://butler.local/problems/{self.code.lower()}",
            "title": self.code.replace("_", " ").title(),
            "status": self.status,
            "code": self.code,
            "reason_code": self.code,
            "detail": self.safe_detail,
            "request_id": request_id,
            "safe_detail": self.safe_detail,
            "actions": list(self.actions),
            "current_version": self.current_version,
        }
        extensions = {
            "conflict_id": self.conflict_id,
            "conflict_version": self.conflict_version,
            "existing_account_id": self.existing_account_id,
            "proposed_account_id": self.proposed_account_id,
        }
        problem.update({key: value for key, value in extensions.items() if value is not None})
        return problem


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    tenant_digest: str
    actor_id: str
    actor_id_digest: str = ""
    session_id_digest: str = ""
    device_id_digest: str = ""
    permission_decision_digest: str = ""
    permission_policy_version: str = "capability-session.v1"
    action: str = "ACCOUNTING_REVIEW_VIEW"
    authorization_decision_id: str = ""
    authorization_policy_version: int | None = None
    authorization_policy_digest: str = ""
    authorization_assertion_digest: str = ""
    authorization_resource_digest: str = ""
    authorization_role: str = ""
    role_registry_version: int = 0
    authorization_company_id: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id or len(self.tenant_id) > 128:
            raise ValueError("TENANT_ID_INVALID")
        if not _DIGEST_RE.fullmatch(self.tenant_digest):
            raise ValueError("TENANT_DIGEST_INVALID")
        if not _ID_RE.fullmatch(self.actor_id):
            raise ValueError("ACTOR_ID_INVALID")
        for value in (
            self.actor_id_digest,
            self.session_id_digest,
            self.device_id_digest,
            self.permission_decision_digest,
            self.authorization_policy_digest,
            self.authorization_assertion_digest,
            self.authorization_resource_digest,
        ):
            if value and not _DIGEST_RE.fullmatch(value):
                raise ValueError("AUTHENTICATED_ACTION_DIGEST_INVALID")
        if self.authorization_decision_id and not _ACCOUNT_RE.fullmatch(
            self.authorization_decision_id
        ):
            raise ValueError("AUTHORIZATION_DECISION_ID_INVALID")
        if self.authorization_policy_version is not None and (
            type(self.authorization_policy_version) is not int
            or not 1 <= self.authorization_policy_version <= 9_007_199_254_740_991
        ):
            raise ValueError("AUTHORIZATION_POLICY_VERSION_INVALID")
        if self.authorization_role and self.authorization_role not in {
            "employee", "manager", "admin"
        }:
            raise ValueError("AUTHORIZATION_ROLE_INVALID")
        if type(self.role_registry_version) is not int or self.role_registry_version < 0:
            raise ValueError("ROLE_REGISTRY_VERSION_INVALID")
        if self.authorization_company_id and len(self.authorization_company_id) > 128:
            raise ValueError("AUTHORIZATION_COMPANY_ID_INVALID")
        if self.request_id and not _ACCOUNT_RE.fullmatch(self.request_id):
            raise ValueError("AUTHORIZATION_REQUEST_ID_INVALID")


@dataclass(frozen=True, slots=True)
class CanonicalReviewTransaction:
    tenant_digest: str
    batch_id: str
    txn_id: str
    source_sequence: int
    booked_date: date
    amount_minor: int
    currency: str
    bank_direction: str
    transaction_version: int
    canonical_descriptor: str
    descriptor_display: str
    display_policy: str
    vendor_match_token: str
    adapter_family: str
    adapter_version: str
    normalization_version: str
    source_record_digest: str
    review_state: ReviewState
    suggestion_account_id: str | None = None
    suggestion_rule_id: str | None = None
    safe_reason: str | None = None
    hmac_key_id: str = ""
    company_scope_digest: str = ""

    def __post_init__(self) -> None:
        if not _DIGEST_RE.fullmatch(self.tenant_digest):
            raise ValueError("TENANT_DIGEST_INVALID")
        if not _ID_RE.fullmatch(self.batch_id) or not _ID_RE.fullmatch(self.txn_id):
            raise ValueError("RESOURCE_ID_INVALID")
        if isinstance(self.source_sequence, bool) or self.source_sequence < 0:
            raise ValueError("SOURCE_SEQUENCE_INVALID")
        if type(self.booked_date) is not date:
            raise ValueError("BOOKED_DATE_INVALID")
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise ValueError("AMOUNT_MINOR_INVALID")
        if self.currency != "KRW" or self.bank_direction not in {"INFLOW", "OUTFLOW"}:
            raise ValueError("MONEY_OR_DIRECTION_INVALID")
        if self.transaction_version < 1:
            raise ValueError("TRANSACTION_VERSION_INVALID")
        if not self.canonical_descriptor or len(self.canonical_descriptor) > 500:
            raise ValueError("CANONICAL_DESCRIPTOR_INVALID")
        if len(self.descriptor_display) > 200 or self.display_policy not in {"PLAIN", "MASKED", "RESTRICTED"}:
            raise ValueError("DISPLAY_PROJECTION_INVALID")
        if not _DIGEST_RE.fullmatch(self.vendor_match_token):
            raise ValueError("VENDOR_MATCH_TOKEN_INVALID")
        if not _DIGEST_RE.fullmatch(self.source_record_digest):
            raise ValueError("SOURCE_RECORD_DIGEST_INVALID")
        if not self.adapter_family or not self.adapter_version:
            raise ValueError("ADAPTER_IDENTITY_INVALID")
        if self.company_scope_digest and not _DIGEST_RE.fullmatch(self.company_scope_digest):
            raise ValueError("COMPANY_SCOPE_DIGEST_INVALID")


@dataclass(frozen=True, slots=True)
class AssignCommand:
    account_id: str
    scope: AssignmentScope
    client_action_id: str
    user_action_nonce: str
    expected_transaction_version: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AssignCommand":
        if set(value) != {
            "account_id",
            "scope",
            "client_action_id",
            "user_action_nonce",
            "expected_transaction_version",
        }:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Unknown or missing assignment field.")
        account_id = value.get("account_id")
        client_action_id = value.get("client_action_id")
        user_action_nonce = value.get("user_action_nonce")
        version = value.get("expected_transaction_version")
        try:
            scope = AssignmentScope(value.get("scope"))
        except (TypeError, ValueError) as exc:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Invalid assignment scope.") from exc
        if not isinstance(account_id, str) or not _ACCOUNT_RE.fullmatch(account_id):
            raise AssignmentError("ACCOUNT_UNKNOWN", 422, "Account identifier is invalid.")
        try:
            if not isinstance(client_action_id, str):
                raise ValueError
            parsed_action_id = __import__("uuid").UUID(client_action_id)
            if str(parsed_action_id) != client_action_id.casefold():
                raise ValueError
        except ValueError as exc:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Client action identifier is invalid.") from exc
        if not isinstance(user_action_nonce, str) or not _NONCE_RE.fullmatch(user_action_nonce):
            raise AssignmentError("NONCE_INVALID", 409, "The user action nonce is invalid.")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            or version > _SAFE_INTEGER
        ):
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Transaction version is invalid.")
        return cls(account_id, scope, client_action_id, user_action_nonce, version)


def require_mutation_headers(idempotency_key: str | None, if_match: str | None) -> tuple[str, int]:
    try:
        if not isinstance(idempotency_key, str):
            raise ValueError
        parsed_key = __import__("uuid").UUID(idempotency_key)
        if str(parsed_key) != idempotency_key.casefold():
            raise ValueError
    except ValueError as exc:
        raise AssignmentError("IDEMPOTENCY_KEY_REQUIRED", 422, "A UUID Idempotency-Key is required.") from exc
    if not isinstance(if_match, str):
        raise AssignmentError("STALE_ASSIGNMENT_VERSION", 409, "If-Match is required.")
    raw = if_match.strip().removeprefix('W/').strip('"')
    if not raw.isdecimal() or int(raw) < 1:
        raise AssignmentError("STALE_ASSIGNMENT_VERSION", 409, "If-Match must contain the transaction version.")
    return idempotency_key, int(raw)
