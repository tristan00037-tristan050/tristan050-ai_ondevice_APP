from __future__ import annotations

import pytest

from butler_pc_core.accounting.classify.models import DecisionState, ReasonCode
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.port import (
    CurrencyExponentReply,
    RuleBasis,
    RuleSelectionReply,
    VendorMatchReply,
    VendorMatchState,
)

from .conftest import RecordingPort, exact_selection, make_transaction


def test_exact_authority_queries_produce_unverified_auto_proposal(transaction, port):
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.AUTO_PROPOSE
    assert draft.reason_code is ReasonCode.AUTO_PROPOSE_EXACT_RULE
    assert draft.account_id == "PL.SGA.ADVERTISING"
    assert draft.rule_id == "MAP-SAAS-ADVERTISING"
    assert draft.confidence_bp == 10_000
    assert port.call_names == [
        "currency_exponent",
        "is_own_account",
        "match_vendor_exact",
        "select_rule",
        "is_known_account",
        "transcript_digest",
    ]


def test_own_account_is_reviewed_before_vendor_query(transaction):
    port = RecordingPort(own_account=True)
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_SELF_TRANSFER
    assert draft.account_id is None
    assert port.call_names == ["currency_exponent", "is_own_account", "transcript_digest"]


def test_vendor_ambiguity_never_selects_rule(transaction):
    port = RecordingPort(vendor=VendorMatchReply(VendorMatchState.AMBIGUOUS))
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_CLASSIFICATION_AMBIGUOUS
    assert "select_rule" not in port.call_names


def test_no_vendor_can_still_resolve_non_account_event(transaction):
    port = RecordingPort(
        vendor=VendorMatchReply(VendorMatchState.NO_MATCH),
        selection=RuleSelectionReply(basis=RuleBasis.NON_ACCOUNT_EVENT, score_bp=10_000),
    )
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_NON_ACCOUNT_EVENT
    assert draft.account_id is None


def test_no_rule_match_requires_evidence_review(transaction):
    port = RecordingPort(
        vendor=VendorMatchReply(VendorMatchState.NO_MATCH),
        selection=RuleSelectionReply(basis=RuleBasis.NO_MATCH),
    )
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT


def test_statistical_candidate_never_auto_proposes_even_at_10000(transaction):
    port = RecordingPort(
        selection=RuleSelectionReply(basis=RuleBasis.STATISTICAL, score_bp=10_000),
    )
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.confidence_bp == 9_999
    assert draft.account_id is None


def test_exact_rule_with_missing_evidence_requires_review(transaction):
    selection = exact_selection()
    selection = RuleSelectionReply(
        basis=selection.basis,
        account_id=selection.account_id,
        rule_id=selection.rule_id,
        rule_digest=selection.rule_digest,
        score_bp=selection.score_bp,
        evidence_complete=False,
    )
    draft = Stage3Classifier().classify(transaction, RecordingPort(selection=selection))
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT


def test_unknown_account_from_exact_rule_blocks_policy_closure(transaction):
    draft = Stage3Classifier().classify(transaction, RecordingPort(known_account=False))
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_POLICY_CLOSURE
    assert draft.account_id is None


def test_krw_exponent_spoof_blocks_before_profile_queries(transaction):
    port = RecordingPort(exponent=2)
    draft = Stage3Classifier().classify(transaction, port)
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_CURRENCY_EXPONENT
    assert port.call_names == ["currency_exponent", "transcript_digest"]


def test_usd_exponent_two_is_accepted():
    tx = make_transaction(currency="USD", currency_registry_version="currency-registry-usd-v1")
    draft = Stage3Classifier().classify(tx, RecordingPort(exponent=2))
    assert draft.state is DecisionState.AUTO_PROPOSE
    assert draft.currency_exponent == 2


def test_non_contract_currency_exponent_reply_is_fail_closed(transaction):
    class NonContractExponentPort(RecordingPort):
        def currency_exponent(self, currency, registry_version):
            self._record(
                "currency_exponent",
                {"currency": currency, "registry_version": registry_version},
            )
            return type("ForeignReply", (), {"exponent": 0})()

    draft = Stage3Classifier().classify(transaction, NonContractExponentPort())
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_AUTHORITY_BINDING
    assert draft.currency_exponent is None


@pytest.mark.parametrize("malformed_exponent", [True, 99, "0"])
def test_malformed_contract_currency_exponent_is_cleared_before_blocking(
    transaction,
    malformed_exponent,
):
    class MalformedExponentPort(RecordingPort):
        def currency_exponent(self, currency, registry_version):
            self._record(
                "currency_exponent",
                {"currency": currency, "registry_version": registry_version},
            )
            reply = object.__new__(CurrencyExponentReply)
            object.__setattr__(reply, "exponent", malformed_exponent)
            return reply

    draft = Stage3Classifier().classify(transaction, MalformedExponentPort())
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_CURRENCY_EXPONENT
    assert draft.currency_exponent is None


def test_port_binding_error_is_fail_closed(transaction):
    draft = Stage3Classifier().classify(
        transaction,
        RecordingPort(fail_on="match_vendor_exact"),
    )
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_AUTHORITY_BINDING
    assert draft.transcript_digest is None


def test_transport_exception_is_fail_closed(transaction):
    class BrokenPort(RecordingPort):
        def match_vendor_exact(self, vendor_token):
            raise OSError("socket closed")

    draft = Stage3Classifier().classify(transaction, BrokenPort())
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_AUTHORITY_BINDING


def test_non_boolean_authority_replies_are_fail_closed(transaction):
    class BadOwnAccountPort(RecordingPort):
        def is_own_account(self, counterparty_account_token):
            return "false"

    class BadKnownAccountPort(RecordingPort):
        def is_known_account(self, account_id):
            return "true"

    for candidate in (BadOwnAccountPort(), BadKnownAccountPort()):
        draft = Stage3Classifier().classify(transaction, candidate)
        assert draft.state is DecisionState.BLOCKED
        assert draft.reason_code is ReasonCode.BLOCK_AUTHORITY_BINDING


def test_non_contract_authority_objects_are_fail_closed(transaction):
    class BadVendorPort(RecordingPort):
        def match_vendor_exact(self, vendor_token):
            return object()

    class BadSelectionPort(RecordingPort):
        def select_rule(self, facts):
            return object()

    for candidate in (BadVendorPort(), BadSelectionPort()):
        draft = Stage3Classifier().classify(transaction, candidate)
        assert draft.state is DecisionState.BLOCKED
        assert draft.reason_code is ReasonCode.BLOCK_AUTHORITY_BINDING


def test_invalid_transcript_is_fail_closed(transaction):
    draft = Stage3Classifier().classify(transaction, RecordingPort(invalid_transcript=True))
    assert draft.state is DecisionState.BLOCKED
    assert draft.reason_code is ReasonCode.BLOCK_TRANSCRIPT_MISMATCH


def test_finalize_payload_is_meta_only(transaction, port):
    draft = Stage3Classifier().classify(transaction, port)
    payload = draft.to_finalize_payload()
    rendered = str(payload)
    assert "tok_vendor" not in rendered
    assert "tok_account" not in rendered
    assert "signature" not in payload
    assert "receipt_id" not in payload
    assert payload["transaction_digest"] == transaction.transaction_digest


def test_classifier_is_stateless_and_has_no_trust_constructor():
    classifier = Stage3Classifier()
    assert vars(classifier) == {}
