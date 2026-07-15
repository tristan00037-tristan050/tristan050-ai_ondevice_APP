"""Area-B runtime values for the Box 5 v3.2 stage-3 classifier.

These Python objects reduce programming mistakes; they are not a security boundary.
Only a separately verified Policy Authority receipt can make a decision trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_RE = re.compile(r"^tok_[A-Za-z0-9_-]{16,128}$")
_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class ClassificationContractError(ValueError):
    """A canonical input or unverified draft violates the Area-B contract."""


class BankDirection(StrEnum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"


class EconomicEventKind(StrEnum):
    NORMAL = "NORMAL"
    REFUND = "REFUND"
    REVERSAL = "REVERSAL"
    CANCELLATION = "CANCELLATION"


class DecisionState(StrEnum):
    AUTO_PROPOSE = "AUTO_PROPOSE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class ReasonCode(StrEnum):
    """Area-B reason values, including three proposed registry extensions.

    The v3.2 handoff registry does not define success, self-transfer, or
    non-account-event values even though its receipt schema always requires a
    reason. Integration must add the values in
    ``PROPOSED_REASON_CODE_EXTENSIONS`` to the signed contract closure before a
    draft containing one can be finalized.
    """

    BLOCK_POLICY_CLOSURE = "BLOCK_POLICY_CLOSURE"
    BLOCK_PROFILE_PROVENANCE = "BLOCK_PROFILE_PROVENANCE"
    BLOCK_AUTHORITY_BINDING = "BLOCK_AUTHORITY_BINDING"
    BLOCK_TRANSCRIPT_MISMATCH = "BLOCK_TRANSCRIPT_MISMATCH"
    BLOCK_RECEIPT_INVALID = "BLOCK_RECEIPT_INVALID"
    BLOCK_CURRENCY_EXPONENT = "BLOCK_CURRENCY_EXPONENT"
    AUTO_PROPOSE_EXACT_RULE = "AUTO_PROPOSE_EXACT_RULE"
    REVIEW_SELF_TRANSFER = "REVIEW_SELF_TRANSFER"
    REVIEW_NON_ACCOUNT_EVENT = "REVIEW_NON_ACCOUNT_EVENT"
    REVIEW_EVIDENCE_INSUFFICIENT = "REVIEW_EVIDENCE_INSUFFICIENT"
    REVIEW_CLASSIFICATION_AMBIGUOUS = "REVIEW_CLASSIFICATION_AMBIGUOUS"


PROPOSED_REASON_CODE_EXTENSIONS = frozenset(
    {
        ReasonCode.AUTO_PROPOSE_EXACT_RULE,
        ReasonCode.REVIEW_SELF_TRANSFER,
        ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
    }
)


def _require_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ClassificationContractError(f"{name}_INVALID")


def _require_token(value: str | None, name: str, *, required: bool) -> None:
    if value is None:
        if required:
            raise ClassificationContractError(f"{name}_REQUIRED")
        return
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise ClassificationContractError(f"{name}_INVALID")


def _require_digest(value: str | None, name: str, *, required: bool = True) -> None:
    if value is None:
        if required:
            raise ClassificationContractError(f"{name}_REQUIRED")
        return
    if not isinstance(value, str) or not _HEX_DIGEST_RE.fullmatch(value):
        raise ClassificationContractError(f"{name}_INVALID")


def _require_digest_tuple(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple):
        raise ClassificationContractError(f"{name}_NOT_TUPLE")
    if len(values) != len(set(values)):
        raise ClassificationContractError(f"{name}_DUPLICATE")
    if len(values) > 128:
        raise ClassificationContractError(f"{name}_TOO_MANY")
    for value in values:
        _require_digest(value, name)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_digest(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalTransactionV2:
    """Non-PII classification view emitted by the common strict parser.

    The Authority independently binds and validates the referenced transaction.
    No raw counterparty, account number, memo, receipt text, file path, or caller
    approval value is representable here.
    """

    tenant_id: str
    company_id: str
    request_id: str
    transaction_id: str
    source_bank_id: str
    booked_date: date
    value_date: date
    direction: BankDirection
    amount_minor: int
    currency: str
    currency_registry_version: str
    transaction_digest: str
    source_record_digest: str
    counterparty_account_token: str | None = None
    vendor_token: str | None = None
    purpose_code: str | None = None
    purpose_evidence_digest: str | None = None
    description_feature_digests: tuple[str, ...] = ()
    evidence_digests: tuple[str, ...] = ()
    service_period_start: date | None = None
    service_period_end: date | None = None
    accounting_period_end: date | None = None
    event_kind: EconomicEventKind = EconomicEventKind.NORMAL
    original_transaction_digest: str | None = None
    adjustment_reason_code: str | None = None
    schema_version: str = field(default="butler.box5.canonical_transaction.v2", init=False)

    def __post_init__(self) -> None:
        for name in ("tenant_id", "company_id", "request_id", "transaction_id", "source_bank_id"):
            _require_id(getattr(self, name), name.upper())
        if not isinstance(self.booked_date, date) or not isinstance(self.value_date, date):
            raise ClassificationContractError("TRANSACTION_DATE_INVALID")
        if not isinstance(self.direction, BankDirection):
            raise ClassificationContractError("BANK_DIRECTION_INVALID")
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise ClassificationContractError("AMOUNT_MINOR_MUST_BE_SIGNED_INTEGER")
        if self.amount_minor == 0:
            raise ClassificationContractError("AMOUNT_MINOR_ZERO")
        if self.direction is BankDirection.OUTFLOW and self.amount_minor >= 0:
            raise ClassificationContractError("OUTFLOW_AMOUNT_SIGN_INVALID")
        if self.direction is BankDirection.INFLOW and self.amount_minor <= 0:
            raise ClassificationContractError("INFLOW_AMOUNT_SIGN_INVALID")
        if not isinstance(self.currency, str) or not _CURRENCY_RE.fullmatch(self.currency):
            raise ClassificationContractError("CURRENCY_INVALID")
        _require_id(self.currency_registry_version, "CURRENCY_REGISTRY_VERSION")
        _require_digest(self.transaction_digest, "TRANSACTION_DIGEST")
        _require_digest(self.source_record_digest, "SOURCE_RECORD_DIGEST")
        _require_token(self.counterparty_account_token, "COUNTERPARTY_ACCOUNT_TOKEN", required=False)
        _require_token(self.vendor_token, "VENDOR_TOKEN", required=False)
        if self.purpose_code is not None and (
            not isinstance(self.purpose_code, str) or not _CODE_RE.fullmatch(self.purpose_code)
        ):
            raise ClassificationContractError("PURPOSE_CODE_INVALID")
        _require_digest(self.purpose_evidence_digest, "PURPOSE_EVIDENCE_DIGEST", required=False)
        _require_digest_tuple(self.description_feature_digests, "DESCRIPTION_FEATURE_DIGEST")
        _require_digest_tuple(self.evidence_digests, "EVIDENCE_DIGEST")
        for name in ("service_period_start", "service_period_end", "accounting_period_end"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, date):
                raise ClassificationContractError(f"{name.upper()}_INVALID")
        if (
            self.service_period_start is not None
            and self.service_period_end is not None
            and self.service_period_end < self.service_period_start
        ):
            raise ClassificationContractError("SERVICE_PERIOD_INVALID")
        if not isinstance(self.event_kind, EconomicEventKind):
            raise ClassificationContractError("EVENT_KIND_INVALID")
        adjustment = self.event_kind is not EconomicEventKind.NORMAL
        if adjustment:
            _require_digest(self.original_transaction_digest, "ORIGINAL_TRANSACTION_DIGEST")
            if not isinstance(self.adjustment_reason_code, str) or not _CODE_RE.fullmatch(
                self.adjustment_reason_code
            ):
                raise ClassificationContractError("ADJUSTMENT_REASON_CODE_REQUIRED")
        elif self.original_transaction_digest is not None or self.adjustment_reason_code is not None:
            raise ClassificationContractError("NORMAL_EVENT_HAS_ADJUSTMENT_FIELDS")

@dataclass(frozen=True, slots=True)
class UnverifiedClassificationDraft:
    """Area-B result that is never sufficient for journal creation by itself."""

    state: DecisionState
    reason_code: ReasonCode
    transaction_digest: str
    currency: str
    currency_exponent: int | None
    transcript_digest: str | None
    account_id: str | None = None
    rule_id: str | None = None
    rule_digest: str | None = None
    confidence_bp: int = 0
    blockers: tuple[ReasonCode, ...] = ()
    warnings: tuple[ReasonCode, ...] = ()
    schema_version: str = field(default="butler.box5.classifier_draft.v1", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.state, DecisionState) or not isinstance(self.reason_code, ReasonCode):
            raise ClassificationContractError("DRAFT_ENUM_INVALID")
        _require_digest(self.transaction_digest, "TRANSACTION_DIGEST")
        if not isinstance(self.currency, str) or not _CURRENCY_RE.fullmatch(self.currency):
            raise ClassificationContractError("DRAFT_CURRENCY_INVALID")
        if self.currency_exponent is not None and (
            isinstance(self.currency_exponent, bool)
            or not isinstance(self.currency_exponent, int)
            or not 0 <= self.currency_exponent <= 3
        ):
            raise ClassificationContractError("DRAFT_CURRENCY_EXPONENT_INVALID")
        _require_digest(self.transcript_digest, "TRANSCRIPT_DIGEST", required=False)
        if self.account_id is not None:
            _require_id(self.account_id, "ACCOUNT_ID")
        if self.rule_id is not None:
            _require_id(self.rule_id, "RULE_ID")
        _require_digest(self.rule_digest, "RULE_DIGEST", required=False)
        if isinstance(self.confidence_bp, bool) or not isinstance(self.confidence_bp, int):
            raise ClassificationContractError("CONFIDENCE_BP_INVALID")
        if not 0 <= self.confidence_bp <= 10_000:
            raise ClassificationContractError("CONFIDENCE_BP_RANGE")
        if not isinstance(self.blockers, tuple) or not isinstance(self.warnings, tuple):
            raise ClassificationContractError("DRAFT_REASONS_NOT_TUPLE")
        if len(self.blockers) != len(set(self.blockers)) or len(self.warnings) != len(set(self.warnings)):
            raise ClassificationContractError("DRAFT_REASON_DUPLICATE")
        if any(not isinstance(value, ReasonCode) for value in (*self.blockers, *self.warnings)):
            raise ClassificationContractError("DRAFT_REASON_INVALID")
        if self.state is DecisionState.AUTO_PROPOSE:
            if not self.account_id or not self.rule_id or not self.rule_digest:
                raise ClassificationContractError("AUTO_PROPOSE_REQUIRES_ACCOUNT_RULE")
            if self.confidence_bp != 10_000:
                raise ClassificationContractError("AUTO_PROPOSE_REQUIRES_EXACT_CONFIDENCE")
            if self.blockers or self.transcript_digest is None or self.currency_exponent is None:
                raise ClassificationContractError("AUTO_PROPOSE_HAS_UNVERIFIED_INPUT")
            if self.reason_code is not ReasonCode.AUTO_PROPOSE_EXACT_RULE:
                raise ClassificationContractError("AUTO_PROPOSE_REASON_INVALID")
        elif self.state is DecisionState.REVIEW_REQUIRED:
            review_reasons = {
                ReasonCode.REVIEW_SELF_TRANSFER,
                ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
                ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
                ReasonCode.REVIEW_CLASSIFICATION_AMBIGUOUS,
            }
            if self.reason_code not in review_reasons:
                raise ClassificationContractError("REVIEW_REASON_INVALID")
            if self.blockers:
                raise ClassificationContractError("REVIEW_HAS_BLOCKER")
            if self.account_id is not None or self.rule_id is not None or self.rule_digest is not None:
                raise ClassificationContractError("REVIEW_HAS_ACCOUNT_RULE")
            if self.transcript_digest is None or self.currency_exponent is None:
                raise ClassificationContractError("REVIEW_HAS_UNVERIFIED_INPUT")
            if self.reason_code not in self.warnings:
                raise ClassificationContractError("REVIEW_REASON_NOT_RECORDED")
        elif self.state is DecisionState.BLOCKED:
            block_reasons = {
                ReasonCode.BLOCK_POLICY_CLOSURE,
                ReasonCode.BLOCK_PROFILE_PROVENANCE,
                ReasonCode.BLOCK_AUTHORITY_BINDING,
                ReasonCode.BLOCK_TRANSCRIPT_MISMATCH,
                ReasonCode.BLOCK_RECEIPT_INVALID,
                ReasonCode.BLOCK_CURRENCY_EXPONENT,
            }
            if self.reason_code not in block_reasons:
                raise ClassificationContractError("BLOCKED_REASON_INVALID")
            if not self.blockers or self.reason_code not in self.blockers:
                raise ClassificationContractError("BLOCKED_REQUIRES_MATCHING_BLOCKER")
            if self.account_id is not None or self.rule_id is not None or self.rule_digest is not None:
                raise ClassificationContractError("BLOCKED_HAS_ACCOUNT_RULE")

    def to_finalize_payload(self) -> dict[str, Any]:
        """Build the safe payload an Authority must independently validate and sign."""
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "account_id": self.account_id,
            "rule_id": self.rule_id,
            "rule_digest": self.rule_digest,
            "reason_code": self.reason_code.value,
            "confidence_bp": self.confidence_bp,
            "currency": self.currency,
            "currency_exponent": self.currency_exponent,
            "transaction_digest": self.transaction_digest,
            "transcript_digest": self.transcript_digest,
            "blockers": [value.value for value in self.blockers],
            "warnings": [value.value for value in self.warnings],
        }

    @property
    def semantic_digest(self) -> str:
        """Determinism digest; deliberately excludes the session transcript."""
        payload = self.to_finalize_payload()
        payload.pop("transcript_digest")
        return stable_digest(payload)
