"""Negative suites for the stage-3 contract closure (F005 registry · F006 canonical · F015 receipt)."""

from __future__ import annotations

from datetime import date

import pytest

from butler_pc_core.accounting.classify.contracts import (
    ReasonRegistryError,
    REASON_REGISTRY_CODES,
    registry_closure_digest,
    emit_reason,
    canonical_transaction_digest,
    validate_decision_receipt,
    build_decision_receipt,
)
from butler_pc_core.accounting.classify.models import (
    BankDirection,
    CanonicalTransactionV2,
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
)

D64 = "a" * 64


def _tx(**overrides) -> CanonicalTransactionV2:
    base = dict(
        tenant_id="t1", company_id="c1", request_id="r1", transaction_id="x1", source_bank_id="b1",
        booked_date=date(2026, 3, 1), value_date=date(2026, 3, 1), direction=BankDirection.OUTFLOW,
        amount_minor=-1000, currency="KRW", currency_registry_version="v1",
        transaction_digest=D64, source_record_digest=D64,
    )
    base.update(overrides)
    return CanonicalTransactionV2(**base)


def _auto_draft() -> UnverifiedClassificationDraft:
    return UnverifiedClassificationDraft(
        state=DecisionState.AUTO_PROPOSE, reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
        transaction_digest=D64, currency="KRW", currency_exponent=0, transcript_digest=D64,
        account_id="acc.rent", rule_id="rule.rent.v1", rule_digest=D64, confidence_bp=10000,
    )


# ---- F005 reason registry ------------------------------------------------

def test_f005_registry_covers_every_reason_code():
    assert {r.value for r in ReasonCode} <= REASON_REGISTRY_CODES
    assert "BLOCK_CLASSIFIER_CONTRACT" in REASON_REGISTRY_CODES  # AC-006


def test_f005_emit_rejects_out_of_registry_reason():
    assert emit_reason("AUTO_PROPOSE_EXACT_RULE") is ReasonCode.AUTO_PROPOSE_EXACT_RULE
    with pytest.raises(ReasonRegistryError, match="REASON_NOT_IN_REGISTRY"):
        emit_reason("MADE_UP_REASON")


def test_f005_closure_digest_is_deterministic():
    assert registry_closure_digest() == registry_closure_digest()
    assert len(registry_closure_digest()) == 64


# ---- F006 canonical transaction schema + digest --------------------------

def test_f006_canonical_digest_is_deterministic_and_schema_valid():
    d1 = canonical_transaction_digest(_tx())
    d2 = canonical_transaction_digest(_tx())
    assert d1 == d2 and len(d1) == 64


def test_f006_receipt_binds_transaction_canonical_digest():
    receipt = build_decision_receipt(_auto_draft(), _tx())
    assert receipt["transaction_canonical_digest"] == canonical_transaction_digest(_tx())
    assert receipt["reason_registry_closure_digest"] == registry_closure_digest()
    assert receipt["journal_auto_post_allowed"] is False


# ---- F015 decision receipt conditional invariants ------------------------

def _valid_auto_receipt() -> dict:
    return build_decision_receipt(_auto_draft(), _tx())


def test_f015_valid_auto_receipt_passes():
    validate_decision_receipt(_valid_auto_receipt())  # no raise


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(account_id=None),                       # AUTO_PROPOSE w/ null account
        lambda r: r.update(rule_id=None),                          # AUTO_PROPOSE w/ null rule
        lambda r: r.update(blockers=["BLOCK_POLICY_CLOSURE"]),     # AUTO_PROPOSE w/ blocker
        lambda r: r.update(warnings=["REVIEW_EVIDENCE_INSUFFICIENT"]),  # F021 warning
        lambda r: r.update(confidence_bp=9000),                    # non-exact confidence
        lambda r: r.update(reason_code="REVIEW_SELF_TRANSFER"),    # wrong reason for AUTO
        lambda r: r.update(reason_code="MADE_UP_REASON"),          # out-of-registry reason
        lambda r: r.update(journal_auto_post_allowed=True),        # lock must stay False
    ],
)
def test_f015_contradictory_auto_receipt_is_rejected(mutate):
    receipt = _valid_auto_receipt()
    mutate(receipt)
    with pytest.raises(ReasonRegistryError, match="DECISION_RECEIPT_SCHEMA_INVALID"):
        validate_decision_receipt(receipt)


def test_f015_blocked_receipt_must_not_carry_account():
    receipt = _valid_auto_receipt()
    receipt.update(
        state="BLOCKED", reason_code="BLOCK_POLICY_CLOSURE",
        blockers=["BLOCK_POLICY_CLOSURE"], warnings=[],
        confidence_bp=0, account_id="acc.rent", rule_id=None, rule_digest=None,
    )
    with pytest.raises(ReasonRegistryError, match="DECISION_RECEIPT_SCHEMA_INVALID"):
        validate_decision_receipt(receipt)
