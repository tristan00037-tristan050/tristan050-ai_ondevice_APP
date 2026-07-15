"""Zero-regression evaluation for the real v3.2 Stage3Classifier call path."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from butler_pc_core.accounting.classify.models import (
    CanonicalTransactionV2,
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
    stable_digest,
)
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.port import PolicyPort


PortFactory = Callable[[CanonicalTransactionV2], PolicyPort]
_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class RegressionViolation(AssertionError):
    """A candidate weakened a protected baseline decision."""


@dataclass(frozen=True, slots=True)
class ExpectedDraft:
    case_id: str
    transaction: CanonicalTransactionV2
    state: DecisionState
    reason_code: ReasonCode
    account_id: str | None = None
    rule_id: str | None = None
    rule_digest: str | None = None

    def __post_init__(self) -> None:
        if self.state is DecisionState.AUTO_PROPOSE and (
            not self.account_id
            or not self.rule_id
            or not isinstance(self.rule_digest, str)
            or not _HEX_DIGEST_RE.fullmatch(self.rule_digest)
        ):
            raise ValueError("REGRESSION_AUTO_PROPOSE_RULE_BINDING_REQUIRED")


@dataclass(frozen=True, slots=True)
class RegressionReceipt:
    total: int
    passed: int
    failed: int
    false_auto_proposals: int
    zero_regression: bool
    case_set_digest: str
    failed_case_ids: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "schema_version": "butler.box5.stage3_regression.v3.2",
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "false_auto_proposals": self.false_auto_proposals,
            "zero_regression": self.zero_regression,
            "case_set_digest": self.case_set_digest,
            "failed_case_ids": list(self.failed_case_ids),
        }


def prove_zero_regression(
    baseline: Iterable[UnverifiedClassificationDraft],
    candidate: Iterable[UnverifiedClassificationDraft],
) -> None:
    before_items = tuple(baseline)
    after_items = tuple(candidate)
    if len(before_items) != len(after_items):
        raise RegressionViolation("REGRESSION_LENGTH_MISMATCH")
    for index, (before, after) in enumerate(zip(before_items, after_items, strict=True)):
        if before.transaction_digest != after.transaction_digest:
            raise RegressionViolation(f"REGRESSION_TRANSACTION_MISMATCH_{index}")
        if before.state is DecisionState.AUTO_PROPOSE and not (
            after.state is DecisionState.AUTO_PROPOSE
            and after.account_id == before.account_id
            and after.rule_id == before.rule_id
            # F022: an account match alone is not zero-regression. A silent change of the
            # applied rule, its digest, the reason, or the confidence must be detected.
            and after.rule_digest == before.rule_digest
            and after.reason_code is before.reason_code
            and after.confidence_bp == before.confidence_bp
        ):
            raise RegressionViolation(f"REGRESSION_AUTO_PROPOSAL_CHANGED_{index}")
        if before.state is DecisionState.BLOCKED and after.state is not DecisionState.BLOCKED:
            raise RegressionViolation(f"REGRESSION_BLOCK_WEAKENED_{index}")
        # F023-adjacent / self-transfer guard: a review (ISOLATED) baseline must stay review
        # with the same reason so a self-transfer cannot silently become a weaker review.
        if before.state is DecisionState.REVIEW_REQUIRED and not (
            after.state is DecisionState.REVIEW_REQUIRED
            and after.reason_code is before.reason_code
        ):
            raise RegressionViolation(f"REGRESSION_REVIEW_WEAKENED_{index}")
        if before.state is not DecisionState.AUTO_PROPOSE and after.state is DecisionState.AUTO_PROPOSE:
            raise RegressionViolation(f"REGRESSION_NEW_AUTO_PROPOSAL_{index}")


def evaluate_regression(
    classifier: Stage3Classifier,
    cases: Iterable[ExpectedDraft],
    *,
    port_factory: PortFactory,
) -> RegressionReceipt:
    materialized = tuple(cases)
    if not materialized:
        raise ValueError("REGRESSION_CASES_REQUIRED")
    if len({case.case_id for case in materialized}) != len(materialized):
        raise ValueError("REGRESSION_CASE_ID_DUPLICATE")
    failed_ids: list[str] = []
    false_auto = 0
    bindings: list[dict[str, str | None]] = []
    for case in materialized:
        draft = classifier.classify(case.transaction, port_factory(case.transaction))
        passed = (
            draft.state is case.state
            and draft.reason_code is case.reason_code
            and draft.account_id == case.account_id
            and draft.rule_id == case.rule_id
            and draft.rule_digest == case.rule_digest
        )
        if not passed:
            failed_ids.append(case.case_id)
            if draft.state is DecisionState.AUTO_PROPOSE and case.state is not DecisionState.AUTO_PROPOSE:
                false_auto += 1
        bindings.append(
            {
                "case_id": case.case_id,
                "transaction_digest": case.transaction.transaction_digest,
                "expected_state": case.state.value,
                "expected_reason": case.reason_code.value,
                "expected_account_id": case.account_id,
                "expected_rule_id": case.rule_id,
                "expected_rule_digest": case.rule_digest,
            }
        )
    failed = len(failed_ids)
    return RegressionReceipt(
        total=len(materialized),
        passed=len(materialized) - failed,
        failed=failed,
        false_auto_proposals=false_auto,
        zero_regression=failed == 0 and false_auto == 0,
        case_set_digest=stable_digest(bindings),
        failed_case_ids=tuple(failed_ids),
    )
