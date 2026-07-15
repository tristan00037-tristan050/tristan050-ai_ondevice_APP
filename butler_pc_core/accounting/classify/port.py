"""Narrow session-bound interface from Area B to the local Policy Authority.

`PolicyPort` is a transport contract, not a trust object. A same-process fake can
influence an unverified draft, but cannot produce the Authority signature required
by the main journal gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .models import (
    BankDirection,
    ClassificationContractError,
    EconomicEventKind,
    ReasonCode,
)


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class VendorMatchState(StrEnum):
    EXACT = "EXACT"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"


class RuleBasis(StrEnum):
    EXACT_DETERMINISTIC = "EXACT_DETERMINISTIC"
    STATISTICAL = "STATISTICAL"
    NON_ACCOUNT_EVENT = "NON_ACCOUNT_EVENT"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CurrencyExponentReply:
    exponent: int

    def __post_init__(self) -> None:
        if isinstance(self.exponent, bool) or not isinstance(self.exponent, int) or not 0 <= self.exponent <= 3:
            raise ClassificationContractError("CURRENCY_EXPONENT_REPLY_INVALID")


@dataclass(frozen=True, slots=True)
class VendorMatchReply:
    state: VendorMatchState
    match_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, VendorMatchState):
            raise ClassificationContractError("VENDOR_MATCH_STATE_INVALID")
        if self.state is VendorMatchState.EXACT:
            if not isinstance(self.match_id, str) or not _ID_RE.fullmatch(self.match_id):
                raise ClassificationContractError("EXACT_VENDOR_MATCH_ID_REQUIRED")
        elif self.match_id is not None:
            raise ClassificationContractError("NON_EXACT_VENDOR_HAS_MATCH_ID")


@dataclass(frozen=True, slots=True)
class RuleFacts:
    direction: BankDirection
    event_kind: EconomicEventKind
    vendor_match_id: str | None
    purpose_code: str | None
    purpose_evidence_digest: str | None
    description_feature_digests: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    service_period_start: str | None
    service_period_end: str | None
    accounting_period_end: str | None


@dataclass(frozen=True, slots=True)
class RuleSelectionReply:
    basis: RuleBasis
    account_id: str | None = None
    rule_id: str | None = None
    rule_digest: str | None = None
    score_bp: int = 0
    evidence_complete: bool = False
    block_reason: ReasonCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.basis, RuleBasis):
            raise ClassificationContractError("RULE_BASIS_INVALID")
        if isinstance(self.score_bp, bool) or not isinstance(self.score_bp, int) or not 0 <= self.score_bp <= 10_000:
            raise ClassificationContractError("RULE_SCORE_INVALID")
        if not isinstance(self.evidence_complete, bool):
            raise ClassificationContractError("EVIDENCE_COMPLETE_INVALID")
        if self.basis is RuleBasis.EXACT_DETERMINISTIC:
            if not all(
                isinstance(value, str) and _ID_RE.fullmatch(value)
                for value in (self.account_id, self.rule_id)
            ):
                raise ClassificationContractError("EXACT_RULE_ACCOUNT_ID_REQUIRED")
            if not isinstance(self.rule_digest, str) or not _HEX_DIGEST_RE.fullmatch(self.rule_digest):
                raise ClassificationContractError("EXACT_RULE_DIGEST_REQUIRED")
            if self.score_bp != 10_000:
                raise ClassificationContractError("EXACT_RULE_SCORE_INVALID")
            if self.block_reason is not None:
                raise ClassificationContractError("EXACT_RULE_HAS_BLOCK_REASON")
        elif self.basis is RuleBasis.BLOCKED:
            allowed = {
                ReasonCode.BLOCK_POLICY_CLOSURE,
                ReasonCode.BLOCK_PROFILE_PROVENANCE,
                ReasonCode.BLOCK_AUTHORITY_BINDING,
                ReasonCode.BLOCK_TRANSCRIPT_MISMATCH,
            }
            if self.block_reason not in allowed:
                raise ClassificationContractError("BLOCKED_RULE_REASON_INVALID")
            if any(value is not None for value in (self.account_id, self.rule_id, self.rule_digest)):
                raise ClassificationContractError("BLOCKED_RULE_HAS_ACCOUNT_FIELDS")
            if self.score_bp != 0 or self.evidence_complete:
                raise ClassificationContractError("BLOCKED_RULE_HAS_POSITIVE_RESULT")
        else:
            if any(value is not None for value in (self.account_id, self.rule_id, self.rule_digest)):
                raise ClassificationContractError("NON_EXACT_RULE_HAS_ACCOUNT_FIELDS")
            if self.block_reason is not None:
                raise ClassificationContractError("NON_BLOCKED_RULE_HAS_BLOCK_REASON")


class PolicyPortError(RuntimeError):
    def __init__(self, reason_code: ReasonCode) -> None:
        allowed = {
            ReasonCode.BLOCK_POLICY_CLOSURE,
            ReasonCode.BLOCK_PROFILE_PROVENANCE,
            ReasonCode.BLOCK_AUTHORITY_BINDING,
            ReasonCode.BLOCK_TRANSCRIPT_MISMATCH,
            ReasonCode.BLOCK_CURRENCY_EXPONENT,
        }
        if reason_code not in allowed:
            raise ValueError("POLICY_PORT_ERROR_REASON_INVALID")
        self.reason_code = reason_code
        super().__init__(reason_code.value)


class PolicyPort(Protocol):
    """A per-request, peer-bound client owned by Area A."""

    def currency_exponent(self, currency: str, registry_version: str) -> CurrencyExponentReply: ...

    def is_own_account(self, counterparty_account_token: str | None) -> bool: ...

    def match_vendor_exact(self, vendor_token: str | None) -> VendorMatchReply: ...

    def select_rule(self, facts: RuleFacts) -> RuleSelectionReply: ...

    def is_known_account(self, account_id: str) -> bool: ...

    def transcript_digest(self) -> str: ...
