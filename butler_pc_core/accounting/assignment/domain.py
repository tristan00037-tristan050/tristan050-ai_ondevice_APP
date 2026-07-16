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


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def opaque_id() -> str:
    return secrets.token_urlsafe(24).replace("-", "_")


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
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NON_EXPENSE_BANK_EVENT = "NON_EXPENSE_BANK_EVENT"
    USER_ASSIGNED = "USER_ASSIGNED"


class RuleState(StrEnum):
    ACTIVE_SUGGESTION = "ACTIVE_SUGGESTION"
    INACTIVE_USER = "INACTIVE_USER"
    INACTIVE_REGISTRY = "INACTIVE_REGISTRY"
    DEGRADED_KEY_ROTATION = "DEGRADED_KEY_ROTATION"


class EventType(StrEnum):
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_SUPERSEDED = "ASSIGNMENT_SUPERSEDED"
    RULE_CREATED = "RULE_CREATED"
    RULE_SUGGESTED = "RULE_SUGGESTED"
    RULE_DEACTIVATED = "RULE_DEACTIVATED"
    RULE_CONFLICT_DETECTED = "RULE_CONFLICT_DETECTED"
    RULE_CONFLICT_RESOLVED = "RULE_CONFLICT_RESOLVED"
    REGISTRY_INVALIDATED = "REGISTRY_INVALIDATED"


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
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.safe_detail = safe_detail[:300]
        self.actions = actions[:5]
        self.current_version = current_version

    def problem(self, request_id: str) -> dict[str, Any]:
        return {
            "type": f"https://butler.local/problems/{self.code.lower()}",
            "title": self.code.replace("_", " ").title(),
            "status": self.status,
            "code": self.code,
            "request_id": request_id,
            "safe_detail": self.safe_detail,
            "actions": list(self.actions),
            "current_version": self.current_version,
        }


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    tenant_digest: str
    actor_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or len(self.tenant_id) > 128:
            raise ValueError("TENANT_ID_INVALID")
        if not _DIGEST_RE.fullmatch(self.tenant_digest):
            raise ValueError("TENANT_DIGEST_INVALID")
        if not _ID_RE.fullmatch(self.actor_id):
            raise ValueError("ACTOR_ID_INVALID")


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
    normalization_version: str
    source_record_digest: str
    review_state: ReviewState
    suggestion_account_id: str | None = None
    suggestion_rule_id: str | None = None
    safe_reason: str | None = None

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


@dataclass(frozen=True, slots=True)
class AssignCommand:
    account_id: str
    scope: AssignmentScope
    registry_digest: str
    expected_transaction_version: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AssignCommand":
        if set(value) != {
            "schema_version",
            "account_id",
            "scope",
            "registry_digest",
            "expected_transaction_version",
        }:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Unknown or missing assignment field.")
        if value.get("schema_version") != "2.0":
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Unsupported assignment schema.")
        account_id = value.get("account_id")
        digest = value.get("registry_digest")
        version = value.get("expected_transaction_version")
        try:
            scope = AssignmentScope(value.get("scope"))
        except (TypeError, ValueError) as exc:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Invalid assignment scope.") from exc
        if not isinstance(account_id, str) or not _ACCOUNT_RE.fullmatch(account_id):
            raise AssignmentError("ACCOUNT_UNKNOWN", 422, "Account identifier is invalid.")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise AssignmentError("REGISTRY_STALE", 409, "A full current registry digest is required.")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Transaction version is invalid.")
        return cls(account_id, scope, digest, version)


def require_mutation_headers(idempotency_key: str | None, if_match: str | None) -> tuple[str, int]:
    if not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 200:
        raise AssignmentError("IDEMPOTENCY_KEY_REQUIRED", 422, "A valid Idempotency-Key is required.")
    if not isinstance(if_match, str):
        raise AssignmentError("TRANSACTION_STALE", 412, "If-Match is required.")
    raw = if_match.strip().removeprefix('W/').strip('"')
    if not raw.isdecimal() or int(raw) < 1:
        raise AssignmentError("TRANSACTION_STALE", 412, "If-Match must contain the transaction version.")
    return idempotency_key, int(raw)
