from __future__ import annotations

import pytest

from butler_pc_core.accounting.classify.account_column import (
    AccountColumnReason,
    AccountColumnResolution,
    AccountColumnState,
)
from butler_pc_core.accounting.classify.models import ReasonCode
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.port import RuleBasis, RuleSelectionReply
from butler_pc_core.accounting.classify.registered_info import (
    LearnedRuleMatch,
    LearnedRuleMatchStatus,
    RegisteredInfoClassifier,
    RegisteredInfoContractError,
    RegisteredInfoDecision,
    RegisteredInfoReason,
    RegisteredReviewState,
)

from .conftest import RecordingPort, digest
from .test_registered_account_column import _compiler, _resolve


def _no_rule() -> LearnedRuleMatch:
    return LearnedRuleMatch(
        LearnedRuleMatchStatus.NO_MATCH,
        RegisteredInfoReason.USER_RULE_NO_MATCH,
    )


def _exact_rule() -> LearnedRuleMatch:
    return LearnedRuleMatch(
        LearnedRuleMatchStatus.EXACT,
        RegisteredInfoReason.USER_RULE_EXACT_MATCH,
        account_id="PL.SGA.ADVERTISING",
        rule_id="rule-registered-001",
        rule_resource_version=1,
    )


def _absent_column() -> AccountColumnResolution:
    return AccountColumnResolution(
        AccountColumnState.ABSENT,
        AccountColumnReason.ACCOUNT_COLUMN_NOT_FOUND,
    )


def test_source_declared_valid_precedes_user_and_legacy_rules(transaction):
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    source = _resolve(_compiler(), "PL.SGA.PAYMENT_FEE")
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=source,
        learned_rule=_exact_rule(),
    )
    assert decision.state is RegisteredReviewState.SOURCE_DECLARED_VALID
    assert decision.account_id == "PL.SGA.PAYMENT_FEE"
    assert decision.final_classification is True
    assert decision.current_assignment_changed is False
    assert decision.journal_auto_post_allowed is False


def test_invalid_explicit_source_does_not_get_silently_replaced_by_rule(transaction):
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    source = _resolve(_compiler(), "유사한 계정 이름")
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=source,
        learned_rule=_exact_rule(),
    )
    assert decision.state is RegisteredReviewState.REVIEW_REQUIRED
    assert decision.account_id is None


def test_user_rule_match_stays_suggested_until_confirmation(transaction):
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_absent_column(),
        learned_rule=_exact_rule(),
    )
    assert decision.state is RegisteredReviewState.USER_RULE_SUGGESTED
    assert decision.requires_user_confirmation is True
    assert decision.final_classification is False
    assert decision.current_assignment_changed is False
    assert decision.journal_auto_post_allowed is False


def test_user_rule_suggestion_cannot_be_constructed_as_final_or_write_authority():
    with pytest.raises(
        RegisteredInfoContractError, match="USER_RULE_SUGGESTION_PROMOTED"
    ):
        RegisteredInfoDecision(
            RegisteredReviewState.USER_RULE_SUGGESTED,
            RegisteredInfoReason.USER_RULE_EXACT_MATCH,
            account_id="PL.SGA.ADVERTISING",
            rule_id="rule-registered-001",
            requires_user_confirmation=False,
            final_classification=True,
        )


def test_decision_state_cannot_carry_a_contradictory_reason():
    with pytest.raises(
        RegisteredInfoContractError, match="REGISTERED_DECISION_REASON_INVALID"
    ):
        RegisteredInfoDecision(
            RegisteredReviewState.REVIEW_REQUIRED,
            RegisteredInfoReason.USER_RULE_EXACT_MATCH,
        )
    with pytest.raises(
        RegisteredInfoContractError, match="ALGORITHM_DECISION_HAS_WRITE_AUTHORITY"
    ):
        RegisteredInfoDecision(
            RegisteredReviewState.USER_RULE_SUGGESTED,
            RegisteredInfoReason.USER_RULE_EXACT_MATCH,
            account_id="PL.SGA.ADVERTISING",
            rule_id="rule-registered-001",
            requires_user_confirmation=True,
            current_assignment_changed=True,
        )


@pytest.mark.parametrize(
    ("port", "reason"),
    [
        (RecordingPort(own_account=True), ReasonCode.REVIEW_SELF_TRANSFER),
        (
            RecordingPort(
                selection=RuleSelectionReply(
                    basis=RuleBasis.NON_ACCOUNT_EVENT,
                    score_bp=10_000,
                )
            ),
            ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
        ),
    ],
)
def test_self_transfer_and_non_account_guards_precede_source_column(
    transaction, port, reason
):
    baseline = Stage3Classifier().classify(transaction, port)
    assert baseline.reason_code is reason
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_resolve(_compiler(), "PL.SGA.ADVERTISING"),
        learned_rule=_exact_rule(),
    )
    assert decision.state is RegisteredReviewState.REVIEW_REQUIRED
    assert decision.account_id is None


def test_policy_block_precedes_every_candidate(transaction):
    baseline = Stage3Classifier().classify(
        transaction,
        RecordingPort(fail_on="currency_exponent"),
    )
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_resolve(_compiler(), "PL.SGA.ADVERTISING"),
        learned_rule=_exact_rule(),
    )
    assert decision.state is RegisteredReviewState.BLOCKED
    assert decision.reason is RegisteredInfoReason.BASELINE_BLOCKED


def test_learned_rule_conflict_and_rotation_block_do_not_fall_through(transaction):
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    conflict = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_absent_column(),
        learned_rule=LearnedRuleMatch(
            LearnedRuleMatchStatus.CONFLICT,
            RegisteredInfoReason.LEARNED_RULE_CONFLICT,
        ),
    )
    blocked = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_absent_column(),
        learned_rule=LearnedRuleMatch(
            LearnedRuleMatchStatus.BLOCKED,
            RegisteredInfoReason.BLOCK_KEY_ROTATION,
        ),
    )
    assert conflict.state is RegisteredReviewState.REVIEW_REQUIRED
    assert blocked.state is RegisteredReviewState.BLOCKED


def test_no_user_rule_falls_back_to_existing_exact_proposal(transaction):
    port = RecordingPort()
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    decision = RegisteredInfoClassifier().classify(
        transaction,
        port,
        account_column=_absent_column(),
        learned_rule=_no_rule(),
    )
    assert decision.state is RegisteredReviewState.AUTO_PROPOSE
    assert decision.account_id == baseline.account_id
    assert decision.requires_user_confirmation is True
    assert decision.final_classification is False


def test_no_user_or_legacy_rule_is_review_required(transaction):
    baseline = Stage3Classifier().classify(
        transaction,
        RecordingPort(selection=RuleSelectionReply(basis=RuleBasis.NO_MATCH)),
    )
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_absent_column(),
        learned_rule=_no_rule(),
    )
    assert decision.state is RegisteredReviewState.REVIEW_REQUIRED
    assert decision.account_id is None


def test_decision_surface_contains_no_token_actor_or_raw_descriptor(transaction):
    baseline = Stage3Classifier().classify(transaction, RecordingPort())
    decision = RegisteredInfoClassifier().decide(
        baseline=baseline,
        account_column=_absent_column(),
        learned_rule=_exact_rule(),
    )
    names = set(decision.__dataclass_fields__)
    assert (
        not {"vendor_match_token", "actor_id", "descriptor_display", "raw_memo"} & names
    )
    assert digest("unrelated") not in repr(decision)
