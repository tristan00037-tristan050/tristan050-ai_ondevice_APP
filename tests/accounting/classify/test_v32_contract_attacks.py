from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest

from butler_pc_core.accounting.classify.models import (
    BankDirection,
    ClassificationContractError,
    DecisionState,
    EconomicEventKind,
    PROPOSED_REASON_CODE_EXTENSIONS,
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

from .conftest import RecordingPort, digest, make_transaction


@pytest.mark.parametrize("amount", [1.5, True, "100"])
def test_float_bool_and_string_money_are_rejected(amount):
    with pytest.raises(ClassificationContractError, match="AMOUNT_MINOR_MUST_BE_SIGNED_INTEGER"):
        make_transaction(amount_minor=amount)


def test_direction_and_signed_amount_must_agree():
    with pytest.raises(ClassificationContractError, match="OUTFLOW_AMOUNT_SIGN_INVALID"):
        make_transaction(amount_minor=100)
    with pytest.raises(ClassificationContractError, match="INFLOW_AMOUNT_SIGN_INVALID"):
        make_transaction(direction=BankDirection.INFLOW, amount_minor=-100)


def test_plain_account_number_cannot_cross_area_b_boundary():
    with pytest.raises(ClassificationContractError, match="COUNTERPARTY_ACCOUNT_TOKEN_INVALID"):
        make_transaction(counterparty_account_token="110-123-456789")


def test_plain_vendor_text_cannot_cross_area_b_boundary():
    with pytest.raises(ClassificationContractError, match="VENDOR_TOKEN_INVALID"):
        make_transaction(vendor_token="Example Vendor")


def test_raw_text_fields_do_not_exist_in_canonical_transaction():
    with pytest.raises(TypeError):
        make_transaction(description="raw memo")
    with pytest.raises(TypeError):
        make_transaction(counterparty_name="raw holder")
    with pytest.raises(TypeError):
        make_transaction(account_number="110123456789")


@pytest.mark.parametrize("kind", [EconomicEventKind.REFUND, EconomicEventKind.REVERSAL, EconomicEventKind.CANCELLATION])
def test_adjustment_requires_original_reference_and_reason(kind):
    with pytest.raises(ClassificationContractError, match="ORIGINAL_TRANSACTION_DIGEST_REQUIRED"):
        make_transaction(event_kind=kind)
    tx = make_transaction(
        event_kind=kind,
        original_transaction_digest=digest("original-transaction"),
        adjustment_reason_code="CUSTOMER_REFUND",
    )
    assert tx.event_kind is kind


def test_normal_event_rejects_adjustment_fields():
    with pytest.raises(ClassificationContractError, match="NORMAL_EVENT_HAS_ADJUSTMENT_FIELDS"):
        make_transaction(original_transaction_digest=digest("unexpected"))


def test_service_period_order_is_validated():
    with pytest.raises(ClassificationContractError, match="SERVICE_PERIOD_INVALID"):
        make_transaction(
            service_period_start=date(2026, 12, 31),
            service_period_end=date(2026, 1, 1),
        )


def test_exact_rule_requires_account_rule_and_digest():
    with pytest.raises(ClassificationContractError, match="EXACT_RULE_ACCOUNT_ID_REQUIRED"):
        RuleSelectionReply(basis=RuleBasis.EXACT_DETERMINISTIC)


def test_exact_rule_requires_exact_score():
    with pytest.raises(ClassificationContractError, match="EXACT_RULE_SCORE_INVALID"):
        RuleSelectionReply(
            basis=RuleBasis.EXACT_DETERMINISTIC,
            account_id="PL.SGA.ADVERTISING",
            rule_id="MAP-SAAS-ADVERTISING",
            rule_digest=digest("rule"),
            score_bp=9_999,
            evidence_complete=True,
        )


def test_non_exact_rule_cannot_smuggle_account():
    with pytest.raises(ClassificationContractError, match="NON_EXACT_RULE_HAS_ACCOUNT_FIELDS"):
        RuleSelectionReply(basis=RuleBasis.STATISTICAL, account_id="PL.SGA.ADVERTISING")


def test_blocked_rule_requires_closed_reason_registry():
    with pytest.raises(ClassificationContractError, match="BLOCKED_RULE_REASON_INVALID"):
        RuleSelectionReply(
            basis=RuleBasis.BLOCKED,
            block_reason=ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
        )


def test_blocked_rule_cannot_smuggle_account_or_positive_result():
    with pytest.raises(ClassificationContractError, match="BLOCKED_RULE_HAS_ACCOUNT_FIELDS"):
        RuleSelectionReply(
            basis=RuleBasis.BLOCKED,
            account_id="PL.SGA.ADVERTISING",
            block_reason=ReasonCode.BLOCK_POLICY_CLOSURE,
        )
    with pytest.raises(ClassificationContractError, match="BLOCKED_RULE_HAS_POSITIVE_RESULT"):
        RuleSelectionReply(
            basis=RuleBasis.BLOCKED,
            score_bp=1,
            block_reason=ReasonCode.BLOCK_POLICY_CLOSURE,
        )


def test_non_exact_vendor_cannot_smuggle_match_id():
    with pytest.raises(ClassificationContractError, match="NON_EXACT_VENDOR_HAS_MATCH_ID"):
        VendorMatchReply(VendorMatchState.NO_MATCH, "fake.match")


def test_auto_proposal_cannot_use_review_reason(transaction):
    with pytest.raises(ClassificationContractError, match="AUTO_PROPOSE_REASON_INVALID"):
        UnverifiedClassificationDraft(
            state=DecisionState.AUTO_PROPOSE,
            reason_code=ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
            transaction_digest=transaction.transaction_digest,
            currency="KRW",
            currency_exponent=0,
            transcript_digest=digest("transcript"),
            account_id="PL.SGA.ADVERTISING",
            rule_id="MAP-SAAS-ADVERTISING",
            rule_digest=digest("rule"),
            confidence_bp=10_000,
        )


def test_auto_proposal_cannot_enable_less_than_exact_confidence(transaction):
    with pytest.raises(ClassificationContractError, match="AUTO_PROPOSE_REQUIRES_EXACT_CONFIDENCE"):
        UnverifiedClassificationDraft(
            state=DecisionState.AUTO_PROPOSE,
            reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
            transaction_digest=transaction.transaction_digest,
            currency="KRW",
            currency_exponent=0,
            transcript_digest=digest("transcript"),
            account_id="PL.SGA.ADVERTISING",
            rule_id="MAP-SAAS-ADVERTISING",
            rule_digest=digest("rule"),
            confidence_bp=9_999,
        )


def test_same_process_fake_port_can_only_create_unverified_draft(transaction):
    draft = Stage3Classifier().classify(transaction, RecordingPort())
    assert isinstance(draft, UnverifiedClassificationDraft)
    assert not hasattr(draft, "signature")
    assert not hasattr(draft, "receipt_id")
    assert not hasattr(draft, "authority")


def test_object_new_spoof_has_no_authority_capability():
    spoof = object.__new__(UnverifiedClassificationDraft)
    assert not hasattr(spoof, "signature")
    with pytest.raises(AttributeError):
        spoof.to_finalize_payload()


def test_copy_pickle_and_proxy_cannot_add_authority_capability(transaction):
    import copy
    import pickle

    draft = Stage3Classifier().classify(transaction, RecordingPort())
    variants = (copy.copy(draft), copy.deepcopy(draft), pickle.loads(pickle.dumps(draft)))
    for value in variants:
        assert value == draft
        assert not hasattr(value, "signature")
        assert not hasattr(value, "receipt_id")


def test_public_classifier_signature_has_no_loose_trust_inputs():
    signature = inspect.signature(Stage3Classifier.classify)
    assert tuple(signature.parameters) == ("self", "tx", "port")
    constructor = inspect.signature(Stage3Classifier)
    assert tuple(constructor.parameters) == ()


def test_unsigned_reason_registry_extensions_are_explicit():
    assert PROPOSED_REASON_CODE_EXTENSIONS == {
        ReasonCode.AUTO_PROPOSE_EXACT_RULE,
        ReasonCode.REVIEW_SELF_TRANSFER,
        ReasonCode.REVIEW_NON_ACCOUNT_EVENT,
    }


def test_area_b_source_has_no_forbidden_boundary_names():
    root = Path(__file__).parents[3] / "butler_pc_core" / "accounting" / "classify"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "expected_manifest_sha",
        "expected_policy_digest",
        "policy_bundle_digest",
        "chart_account_ids",
        "approval_status",
        "approval_id",
        "is_verified",
        "company_account_numbers",
        "raw_policy_dict",
        "trust_public_key",
        "CompanyProfileRuntime",
        "descriptor_hmac_key",
    )
    assert [name for name in forbidden if name in source] == []


def test_area_b_has_no_receipt_or_journal_gate_implementation():
    assert not hasattr(Stage3Classifier, "verify_receipt")
    assert not hasattr(Stage3Classifier, "post_journal")
