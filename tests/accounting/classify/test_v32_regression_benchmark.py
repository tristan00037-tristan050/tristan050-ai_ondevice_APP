from __future__ import annotations

import pytest

from butler_pc_core.accounting.classify.models import (
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
)
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.port import (
    RuleBasis,
    RuleSelectionReply,
    VendorMatchReply,
    VendorMatchState,
)
from butler_pc_core.accounting.eval import (
    ExpectedDraft,
    RegressionViolation,
    evaluate_regression,
    prove_zero_regression,
    run_classifier_benchmark,
)

from .conftest import RecordingPort, digest, make_transaction


def port_factory(tx):
    if tx.transaction_id.startswith("own-"):
        return RecordingPort(own_account=True)
    if tx.transaction_id.startswith("unknown-"):
        return RecordingPort(
            vendor=VendorMatchReply(VendorMatchState.NO_MATCH),
            selection=RuleSelectionReply(basis=RuleBasis.NO_MATCH),
        )
    if tx.transaction_id.startswith("event-"):
        return RecordingPort(
            vendor=VendorMatchReply(VendorMatchState.NO_MATCH),
            selection=RuleSelectionReply(basis=RuleBasis.NON_ACCOUNT_EVENT, score_bp=10_000),
        )
    if tx.transaction_id.startswith("blocked-"):
        return RecordingPort(exponent=2)
    return RecordingPort()


def regression_cases():
    cases = []
    for index in range(10):
        tx = make_transaction(
            transaction_id=f"exact-{index:02d}",
            transaction_digest=digest(f"exact-{index:02d}"),
        )
        cases.append(
            ExpectedDraft(
                case_id=f"exact-{index:02d}",
                transaction=tx,
                state=DecisionState.AUTO_PROPOSE,
                reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
                account_id="PL.SGA.ADVERTISING",
                rule_id="MAP-SAAS-ADVERTISING",
                rule_digest=digest("rule-advertising"),
            )
        )
    for index in range(10):
        tx = make_transaction(
            transaction_id=f"own-{index:02d}",
            transaction_digest=digest(f"own-{index:02d}"),
        )
        cases.append(
            ExpectedDraft(
                case_id=f"own-{index:02d}",
                transaction=tx,
                state=DecisionState.REVIEW_REQUIRED,
                reason_code=ReasonCode.REVIEW_SELF_TRANSFER,
            )
        )
    for index in range(8):
        tx = make_transaction(
            transaction_id=f"unknown-{index:02d}",
            transaction_digest=digest(f"unknown-{index:02d}"),
        )
        cases.append(
            ExpectedDraft(
                case_id=f"unknown-{index:02d}",
                transaction=tx,
                state=DecisionState.REVIEW_REQUIRED,
                reason_code=ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
            )
        )
    for index in range(4):
        tx = make_transaction(
            transaction_id=f"event-{index:02d}",
            transaction_digest=digest(f"event-{index:02d}"),
        )
        cases.append(
            ExpectedDraft(
                case_id=f"event-{index:02d}",
                transaction=tx,
                state=DecisionState.REVIEW_REQUIRED,
                reason_code=ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
            )
        )
    for index in range(4):
        tx = make_transaction(
            transaction_id=f"blocked-{index:02d}",
            transaction_digest=digest(f"blocked-{index:02d}"),
        )
        cases.append(
            ExpectedDraft(
                case_id=f"blocked-{index:02d}",
                transaction=tx,
                state=DecisionState.BLOCKED,
                reason_code=ReasonCode.BLOCK_CURRENCY_EXPONENT,
            )
        )
    return cases


def test_36_case_regression_on_actual_classifier():
    receipt = evaluate_regression(
        Stage3Classifier(),
        regression_cases(),
        port_factory=port_factory,
    )
    assert receipt.total == 36
    assert receipt.passed == 36
    assert receipt.failed == 0
    assert receipt.false_auto_proposals == 0
    assert receipt.zero_regression is True


def test_actual_draft_replay_is_semantically_deterministic():
    classifier = Stage3Classifier()
    tx = make_transaction()
    digests = {
        classifier.classify(tx, RecordingPort()).semantic_digest
        for _ in range(100)
    }
    assert len(digests) == 1


def test_auto_propose_regression_case_requires_rule_digest():
    tx = make_transaction(transaction_digest=digest("missing-rule-digest"))
    with pytest.raises(ValueError, match="REGRESSION_AUTO_PROPOSE_RULE_BINDING_REQUIRED"):
        ExpectedDraft(
            case_id="missing-rule-digest",
            transaction=tx,
            state=DecisionState.AUTO_PROPOSE,
            reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
            account_id="PL.SGA.ADVERTISING",
            rule_id="MAP-SAAS-ADVERTISING",
        )


def test_evaluate_regression_detects_silent_rule_body_drift():
    tx = make_transaction(transaction_digest=digest("rule-body-drift"))
    case = ExpectedDraft(
        case_id="rule-body-drift",
        transaction=tx,
        state=DecisionState.AUTO_PROPOSE,
        reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
        account_id="PL.SGA.ADVERTISING",
        rule_id="MAP-SAAS-ADVERTISING",
        rule_digest=digest("rule-advertising"),
    )
    selection = RuleSelectionReply(
        basis=RuleBasis.EXACT_DETERMINISTIC,
        account_id="PL.SGA.ADVERTISING",
        rule_id="MAP-SAAS-ADVERTISING",
        rule_digest=digest("rule-advertising-mutated"),
        score_bp=10_000,
        evidence_complete=True,
    )
    receipt = evaluate_regression(
        Stage3Classifier(),
        [case],
        port_factory=lambda _: RecordingPort(selection=selection),
    )
    assert receipt.failed == 1
    assert receipt.failed_case_ids == ("rule-body-drift",)
    assert receipt.zero_regression is False


def test_regression_rejects_block_weakening():
    tx = make_transaction(transaction_digest=digest("blocked-baseline"))
    before = Stage3Classifier().classify(tx, RecordingPort(exponent=2))
    after = UnverifiedClassificationDraft(
        state=DecisionState.REVIEW_REQUIRED,
        reason_code=ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
        transaction_digest=tx.transaction_digest,
        currency="KRW",
        currency_exponent=0,
        transcript_digest=digest("after-transcript"),
        warnings=(ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,),
    )
    with pytest.raises(RegressionViolation, match="REGRESSION_BLOCK_WEAKENED"):
        prove_zero_regression([before], [after])


def test_benchmark_reports_tail_latency_failures_and_replay():
    transactions = [
        make_transaction(transaction_id="exact-bench", transaction_digest=digest("exact-bench")),
        make_transaction(transaction_id="own-bench", transaction_digest=digest("own-bench")),
        make_transaction(transaction_id="unknown-bench", transaction_digest=digest("unknown-bench")),
        make_transaction(transaction_id="event-bench", transaction_digest=digest("event-bench")),
    ]
    receipt = run_classifier_benchmark(
        Stage3Classifier(),
        transactions,
        port_factory=port_factory,
        warmup_iterations=2,
        measured_iterations=25,
    )
    assert receipt.samples == 100
    assert receipt.failure_count == 0
    assert receipt.deterministic_replay is True
    assert receipt.p50_us <= receipt.p90_us <= receipt.p95_us <= receipt.p99_us <= receipt.max_us
    assert receipt.classifier_contract_version == "butler.box5.stage3_classifier.v3.2"
