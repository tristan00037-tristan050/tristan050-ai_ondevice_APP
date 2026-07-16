"""Registered-account and learned-rule decision layer for the Box5 product.

The layer consumes strict, server-created values only.  It cannot write an
assignment, create a rule, issue a receipt, or authorize journal posting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence

from .account_column import (
    AccountColumnContractError,
    AccountColumnResolution,
    AccountColumnState,
    AccountRegistrySnapshot,
)
from .models import (
    CanonicalTransactionV2,
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
)
from .pipeline import Stage3Classifier
from .port import PolicyPort
from .vendor_match import VendorMatchTokenSet


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN_RE = re.compile(r"^tok_[A-Za-z0-9_-]{43}$")


class RegisteredInfoContractError(ValueError):
    """A learned-rule or review decision crossed an invalid trust boundary."""


class LearnedRuleState(StrEnum):
    ACTIVE_SUGGESTION = "ACTIVE_SUGGESTION"
    INACTIVE_USER = "INACTIVE_USER"
    INACTIVE_REGISTRY = "INACTIVE_REGISTRY"
    DEGRADED_KEY_ROTATION = "DEGRADED_KEY_ROTATION"


class LearnedRuleMatchStatus(StrEnum):
    NO_MATCH = "NO_MATCH"
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"


class RegisteredReviewState(StrEnum):
    SOURCE_DECLARED_VALID = "SOURCE_DECLARED_VALID"
    AUTO_PROPOSE = "AUTO_PROPOSE"
    USER_RULE_SUGGESTED = "USER_RULE_SUGGESTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class RegisteredInfoReason(StrEnum):
    SOURCE_ACCOUNT_ACCEPTED = "SOURCE_ACCOUNT_ACCEPTED"
    USER_RULE_EXACT_MATCH = "USER_RULE_EXACT_MATCH"
    USER_RULE_NO_MATCH = "USER_RULE_NO_MATCH"
    LEARNED_RULE_CONFLICT = "LEARNED_RULE_CONFLICT"
    BLOCK_TENANT_BOUNDARY = "BLOCK_TENANT_BOUNDARY"
    BLOCK_RULE_CONTRACT = "BLOCK_RULE_CONTRACT"
    BLOCK_REGISTRY_STALE = "BLOCK_REGISTRY_STALE"
    BLOCK_KEY_ROTATION = "BLOCK_KEY_ROTATION"
    BLOCK_ACCOUNT_NONASSIGNABLE = "BLOCK_ACCOUNT_NONASSIGNABLE"
    BASELINE_AUTO_PROPOSE = "BASELINE_AUTO_PROPOSE"
    BASELINE_REVIEW_REQUIRED = "BASELINE_REVIEW_REQUIRED"
    BASELINE_BLOCKED = "BASELINE_BLOCKED"


def _require_digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise RegisteredInfoContractError(f"{name}_INVALID")


def _require_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise RegisteredInfoContractError(f"{name}_INVALID")


@dataclass(frozen=True, slots=True)
class LearnedRuleCandidate:
    """Safe projection read from the assignment team's tenant-scoped rule store."""

    rule_id: str
    tenant_digest: str
    account_id: str
    state: LearnedRuleState
    registry_digest: str
    overlay_digest: str
    match_key_id: str
    normalization_version: str
    adapter_family: str
    descriptor_schema_version: str
    resource_version: int
    vendor_match_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value, name in (
            (self.rule_id, "RULE_ID"),
            (self.account_id, "ACCOUNT_ID"),
            (self.match_key_id, "MATCH_KEY_ID"),
            (self.normalization_version, "NORMALIZATION_VERSION"),
            (self.adapter_family, "ADAPTER_FAMILY"),
            (self.descriptor_schema_version, "DESCRIPTOR_SCHEMA_VERSION"),
        ):
            _require_id(value, name)
        for value, name in (
            (self.tenant_digest, "TENANT_DIGEST"),
            (self.registry_digest, "REGISTRY_DIGEST"),
            (self.overlay_digest, "OVERLAY_DIGEST"),
        ):
            _require_digest(value, name)
        if not isinstance(self.state, LearnedRuleState):
            raise RegisteredInfoContractError("LEARNED_RULE_STATE_INVALID")
        if not isinstance(self.vendor_match_token, str) or not _TOKEN_RE.fullmatch(
            self.vendor_match_token
        ):
            raise RegisteredInfoContractError("VENDOR_MATCH_TOKEN_INVALID")
        if (
            isinstance(self.resource_version, bool)
            or not isinstance(self.resource_version, int)
            or self.resource_version < 1
        ):
            raise RegisteredInfoContractError("RULE_RESOURCE_VERSION_INVALID")


@dataclass(frozen=True, slots=True)
class LearnedRuleMatch:
    status: LearnedRuleMatchStatus
    reason: RegisteredInfoReason
    account_id: str | None = None
    rule_id: str | None = None
    rule_resource_version: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LearnedRuleMatchStatus) or not isinstance(
            self.reason, RegisteredInfoReason
        ):
            raise RegisteredInfoContractError("RULE_MATCH_ENUM_INVALID")
        if self.status is LearnedRuleMatchStatus.EXACT:
            if (
                self.account_id is None
                or self.rule_id is None
                or self.rule_resource_version is None
            ):
                raise RegisteredInfoContractError("EXACT_RULE_MATCH_INCOMPLETE")
            _require_id(self.account_id, "ACCOUNT_ID")
            _require_id(self.rule_id, "RULE_ID")
            if (
                isinstance(self.rule_resource_version, bool)
                or not isinstance(self.rule_resource_version, int)
                or self.rule_resource_version < 1
            ):
                raise RegisteredInfoContractError("RULE_RESOURCE_VERSION_INVALID")
        elif any(
            value is not None
            for value in (self.account_id, self.rule_id, self.rule_resource_version)
        ):
            raise RegisteredInfoContractError("NON_EXACT_RULE_MATCH_HAS_SELECTION")
        expected_reason = {
            LearnedRuleMatchStatus.NO_MATCH: {
                RegisteredInfoReason.USER_RULE_NO_MATCH,
            },
            LearnedRuleMatchStatus.EXACT: {
                RegisteredInfoReason.USER_RULE_EXACT_MATCH,
            },
            LearnedRuleMatchStatus.CONFLICT: {
                RegisteredInfoReason.LEARNED_RULE_CONFLICT,
            },
            LearnedRuleMatchStatus.BLOCKED: {
                RegisteredInfoReason.BLOCK_TENANT_BOUNDARY,
                RegisteredInfoReason.BLOCK_RULE_CONTRACT,
                RegisteredInfoReason.BLOCK_REGISTRY_STALE,
                RegisteredInfoReason.BLOCK_KEY_ROTATION,
                RegisteredInfoReason.BLOCK_ACCOUNT_NONASSIGNABLE,
            },
        }[self.status]
        if self.reason not in expected_reason:
            raise RegisteredInfoContractError("RULE_MATCH_REASON_INVALID")


class LearnedRuleMatcher:
    """Exact-only, tenant-bound matching with dual-read/new-write key rotation."""

    CONTRACT_VERSION = "butler.learned_rule_matcher.v2.1"

    def match(
        self,
        *,
        tenant_digest: str,
        tokens: VendorMatchTokenSet,
        candidates: Sequence[LearnedRuleCandidate],
        registry: AccountRegistrySnapshot,
    ) -> LearnedRuleMatch:
        _require_digest(tenant_digest, "TENANT_DIGEST")
        if not isinstance(tokens, VendorMatchTokenSet):
            raise RegisteredInfoContractError("VENDOR_TOKEN_SET_INVALID")
        if not isinstance(registry, AccountRegistrySnapshot):
            raise RegisteredInfoContractError("ACCOUNT_REGISTRY_INVALID")
        if len(candidates) > 128:
            raise RegisteredInfoContractError("LEARNED_RULE_CANDIDATE_LIMIT")
        if any(
            not isinstance(candidate, LearnedRuleCandidate) for candidate in candidates
        ):
            raise RegisteredInfoContractError("LEARNED_RULE_CANDIDATE_INVALID")
        if any(candidate.tenant_digest != tenant_digest for candidate in candidates):
            return LearnedRuleMatch(
                LearnedRuleMatchStatus.BLOCKED,
                RegisteredInfoReason.BLOCK_TENANT_BOUNDARY,
            )

        exact: list[LearnedRuleCandidate] = []
        degraded_match = False
        for candidate in candidates:
            token_value_match = next(
                (
                    token
                    for token in tokens.read_tokens
                    if token.key_id == candidate.match_key_id
                    and token.matches_storage_value(candidate.vendor_match_token)
                ),
                None,
            )
            if token_value_match is not None and (
                token_value_match.adapter_family != candidate.adapter_family
                or token_value_match.descriptor_schema_version
                != candidate.descriptor_schema_version
                or token_value_match.normalization_version
                != candidate.normalization_version
            ):
                return LearnedRuleMatch(
                    LearnedRuleMatchStatus.BLOCKED,
                    RegisteredInfoReason.BLOCK_RULE_CONTRACT,
                )
            matched_token = next(
                (
                    token
                    for token in tokens.read_tokens
                    if token.key_id == candidate.match_key_id
                    and token.adapter_family == candidate.adapter_family
                    and token.descriptor_schema_version
                    == candidate.descriptor_schema_version
                    and token.normalization_version == candidate.normalization_version
                    and token.matches_storage_value(candidate.vendor_match_token)
                ),
                None,
            )
            if matched_token is None:
                continue
            if candidate.state is LearnedRuleState.DEGRADED_KEY_ROTATION:
                degraded_match = True
                continue
            if candidate.state is not LearnedRuleState.ACTIVE_SUGGESTION:
                continue
            if (
                candidate.registry_digest != registry.registry_digest
                or candidate.overlay_digest != registry.overlay_digest
            ):
                return LearnedRuleMatch(
                    LearnedRuleMatchStatus.BLOCKED,
                    RegisteredInfoReason.BLOCK_REGISTRY_STALE,
                )
            try:
                registry.require_assignable(candidate.account_id)
            except AccountColumnContractError:
                return LearnedRuleMatch(
                    LearnedRuleMatchStatus.BLOCKED,
                    RegisteredInfoReason.BLOCK_ACCOUNT_NONASSIGNABLE,
                )
            exact.append(candidate)

        if degraded_match:
            return LearnedRuleMatch(
                LearnedRuleMatchStatus.BLOCKED,
                RegisteredInfoReason.BLOCK_KEY_ROTATION,
            )
        if not exact:
            return LearnedRuleMatch(
                LearnedRuleMatchStatus.NO_MATCH,
                RegisteredInfoReason.USER_RULE_NO_MATCH,
            )
        semantic_keys = {
            (candidate.rule_id, candidate.account_id, candidate.resource_version)
            for candidate in exact
        }
        if len(exact) != 1 or len(semantic_keys) != 1:
            return LearnedRuleMatch(
                LearnedRuleMatchStatus.CONFLICT,
                RegisteredInfoReason.LEARNED_RULE_CONFLICT,
            )
        selected = exact[0]
        return LearnedRuleMatch(
            LearnedRuleMatchStatus.EXACT,
            RegisteredInfoReason.USER_RULE_EXACT_MATCH,
            account_id=selected.account_id,
            rule_id=selected.rule_id,
            rule_resource_version=selected.resource_version,
        )


@dataclass(frozen=True, slots=True)
class RegisteredInfoDecision:
    state: RegisteredReviewState
    reason: RegisteredInfoReason
    account_id: str | None = None
    rule_id: str | None = None
    source_receipt_digest: str | None = None
    requires_user_confirmation: bool = False
    current_assignment_changed: bool = False
    final_classification: bool = False
    journal_auto_post_allowed: bool = field(default=False, init=False)
    schema_version: str = field(
        default="butler.registered_info_decision.v2.1", init=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.state, RegisteredReviewState) or not isinstance(
            self.reason, RegisteredInfoReason
        ):
            raise RegisteredInfoContractError("REGISTERED_DECISION_ENUM_INVALID")
        for value, name in (
            (self.requires_user_confirmation, "REQUIRES_USER_CONFIRMATION"),
            (self.current_assignment_changed, "CURRENT_ASSIGNMENT_CHANGED"),
            (self.final_classification, "FINAL_CLASSIFICATION"),
        ):
            if not isinstance(value, bool):
                raise RegisteredInfoContractError(f"{name}_INVALID")
        if self.account_id is not None:
            _require_id(self.account_id, "ACCOUNT_ID")
        if self.rule_id is not None:
            _require_id(self.rule_id, "RULE_ID")
        if self.source_receipt_digest is not None:
            _require_digest(self.source_receipt_digest, "SOURCE_RECEIPT_DIGEST")
        if self.current_assignment_changed or self.journal_auto_post_allowed:
            raise RegisteredInfoContractError("ALGORITHM_DECISION_HAS_WRITE_AUTHORITY")
        if self.state is RegisteredReviewState.SOURCE_DECLARED_VALID:
            if self.account_id is None or self.source_receipt_digest is None:
                raise RegisteredInfoContractError("SOURCE_DECLARED_DECISION_INCOMPLETE")
            if not self.final_classification or self.requires_user_confirmation:
                raise RegisteredInfoContractError(
                    "SOURCE_DECLARED_DECISION_STATE_INVALID"
                )
        elif self.state is RegisteredReviewState.USER_RULE_SUGGESTED:
            if self.account_id is None or self.rule_id is None:
                raise RegisteredInfoContractError("USER_RULE_SUGGESTION_INCOMPLETE")
            if self.final_classification or not self.requires_user_confirmation:
                raise RegisteredInfoContractError("USER_RULE_SUGGESTION_PROMOTED")
        elif self.state is RegisteredReviewState.AUTO_PROPOSE:
            if self.account_id is None or self.rule_id is None:
                raise RegisteredInfoContractError("AUTO_PROPOSE_DECISION_INCOMPLETE")
            if self.final_classification or not self.requires_user_confirmation:
                raise RegisteredInfoContractError("AUTO_PROPOSE_PROMOTED")
        elif any(value is not None for value in (self.account_id, self.rule_id)):
            raise RegisteredInfoContractError("NON_SELECTION_DECISION_HAS_ACCOUNT")
        expected_reason = {
            RegisteredReviewState.SOURCE_DECLARED_VALID: {
                RegisteredInfoReason.SOURCE_ACCOUNT_ACCEPTED,
            },
            RegisteredReviewState.AUTO_PROPOSE: {
                RegisteredInfoReason.BASELINE_AUTO_PROPOSE,
            },
            RegisteredReviewState.USER_RULE_SUGGESTED: {
                RegisteredInfoReason.USER_RULE_EXACT_MATCH,
            },
            RegisteredReviewState.REVIEW_REQUIRED: {
                RegisteredInfoReason.BASELINE_REVIEW_REQUIRED,
                RegisteredInfoReason.LEARNED_RULE_CONFLICT,
            },
            RegisteredReviewState.BLOCKED: {
                RegisteredInfoReason.BASELINE_BLOCKED,
                RegisteredInfoReason.BLOCK_TENANT_BOUNDARY,
                RegisteredInfoReason.BLOCK_RULE_CONTRACT,
                RegisteredInfoReason.BLOCK_REGISTRY_STALE,
                RegisteredInfoReason.BLOCK_KEY_ROTATION,
                RegisteredInfoReason.BLOCK_ACCOUNT_NONASSIGNABLE,
            },
        }[self.state]
        if self.reason not in expected_reason:
            raise RegisteredInfoContractError("REGISTERED_DECISION_REASON_INVALID")


class RegisteredInfoClassifier:
    """Apply the v2.1 precedence without adding persistence or trust authority."""

    CONTRACT_VERSION = "butler.registered_info_classifier.v2.1"

    def classify(
        self,
        tx: CanonicalTransactionV2,
        port: PolicyPort,
        *,
        account_column: AccountColumnResolution,
        learned_rule: LearnedRuleMatch,
    ) -> RegisteredInfoDecision:
        """Canonical product entrypoint layered on the existing Stage3 pipeline."""

        if not isinstance(tx, CanonicalTransactionV2):
            raise RegisteredInfoContractError("CANONICAL_TRANSACTION_INVALID")
        baseline = Stage3Classifier().classify(tx, port)
        return self.decide(
            baseline=baseline,
            account_column=account_column,
            learned_rule=learned_rule,
        )

    def decide(
        self,
        *,
        baseline: UnverifiedClassificationDraft,
        account_column: AccountColumnResolution,
        learned_rule: LearnedRuleMatch,
    ) -> RegisteredInfoDecision:
        if not isinstance(baseline, UnverifiedClassificationDraft):
            raise RegisteredInfoContractError("BASELINE_DRAFT_INVALID")
        if not isinstance(account_column, AccountColumnResolution):
            raise RegisteredInfoContractError("ACCOUNT_COLUMN_RESULT_INVALID")
        if not isinstance(learned_rule, LearnedRuleMatch):
            raise RegisteredInfoContractError("LEARNED_RULE_MATCH_INVALID")

        # Policy/authority blocks and self-transfer/non-account guards precede
        # source declarations exactly as required by the v2.1 state machine.
        if baseline.state is DecisionState.BLOCKED:
            return RegisteredInfoDecision(
                RegisteredReviewState.BLOCKED,
                RegisteredInfoReason.BASELINE_BLOCKED,
            )
        if baseline.reason_code in {
            ReasonCode.REVIEW_SELF_TRANSFER,
            ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
        }:
            return RegisteredInfoDecision(
                RegisteredReviewState.REVIEW_REQUIRED,
                RegisteredInfoReason.BASELINE_REVIEW_REQUIRED,
            )

        if account_column.state is AccountColumnState.SOURCE_DECLARED_VALID:
            if account_column.receipt is None:
                raise RegisteredInfoContractError("SOURCE_ACCOUNT_RECEIPT_REQUIRED")
            return RegisteredInfoDecision(
                RegisteredReviewState.SOURCE_DECLARED_VALID,
                RegisteredInfoReason.SOURCE_ACCOUNT_ACCEPTED,
                account_id=account_column.account_id,
                source_receipt_digest=account_column.receipt.digest,
                final_classification=True,
            )
        if account_column.state is AccountColumnState.REVIEW_REQUIRED:
            return RegisteredInfoDecision(
                RegisteredReviewState.REVIEW_REQUIRED,
                RegisteredInfoReason.BASELINE_REVIEW_REQUIRED,
            )

        if learned_rule.status is LearnedRuleMatchStatus.BLOCKED:
            return RegisteredInfoDecision(
                RegisteredReviewState.BLOCKED,
                learned_rule.reason,
            )
        if learned_rule.status is LearnedRuleMatchStatus.CONFLICT:
            return RegisteredInfoDecision(
                RegisteredReviewState.REVIEW_REQUIRED,
                RegisteredInfoReason.LEARNED_RULE_CONFLICT,
            )
        if learned_rule.status is LearnedRuleMatchStatus.EXACT:
            return RegisteredInfoDecision(
                RegisteredReviewState.USER_RULE_SUGGESTED,
                RegisteredInfoReason.USER_RULE_EXACT_MATCH,
                account_id=learned_rule.account_id,
                rule_id=learned_rule.rule_id,
                requires_user_confirmation=True,
            )

        if baseline.state is DecisionState.AUTO_PROPOSE:
            return RegisteredInfoDecision(
                RegisteredReviewState.AUTO_PROPOSE,
                RegisteredInfoReason.BASELINE_AUTO_PROPOSE,
                account_id=baseline.account_id,
                rule_id=baseline.rule_id,
                requires_user_confirmation=True,
            )
        return RegisteredInfoDecision(
            RegisteredReviewState.REVIEW_REQUIRED,
            RegisteredInfoReason.BASELINE_REVIEW_REQUIRED,
        )
