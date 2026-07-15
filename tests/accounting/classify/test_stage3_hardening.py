"""Negative suites for the reproduced code-level defects (F019 date · F020 amount · F021 warning · F022 regression)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from butler_pc_core.accounting.classify.models import (
    BankDirection,
    CanonicalTransactionV2,
    ClassificationContractError,
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
)
from butler_pc_core.accounting.eval.regression import prove_zero_regression, RegressionViolation

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


def _auto(**overrides) -> UnverifiedClassificationDraft:
    base = dict(
        state=DecisionState.AUTO_PROPOSE, reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
        transaction_digest=D64, currency="KRW", currency_exponent=0, transcript_digest=D64,
        account_id="acc.rent", rule_id="rule.rent.v1", rule_digest=D64, confidence_bp=10000,
    )
    base.update(overrides)
    return UnverifiedClassificationDraft(**base)


# ---- F019 datetime must not pass a date field ---------------------------

def test_f019_datetime_rejected_in_booked_date():
    with pytest.raises(ClassificationContractError, match="TRANSACTION_DATE_INVALID"):
        _tx(booked_date=datetime(2026, 3, 1))


def test_f019_datetime_rejected_in_period_fields():
    with pytest.raises(ClassificationContractError, match="SERVICE_PERIOD_START_INVALID"):
        _tx(service_period_start=datetime(2026, 3, 1))


def test_f019_plain_date_still_accepted():
    _tx(booked_date=date(2026, 3, 1))  # no raise


# ---- F020 amount range + business cap ------------------------------------

def test_f020_huge_amount_rejected():
    with pytest.raises(ClassificationContractError, match="AMOUNT_OUT_OF_RANGE_64BIT"):
        _tx(amount_minor=-(10**200))


def test_f020_over_business_cap_rejected():
    with pytest.raises(ClassificationContractError, match="AMOUNT_EXCEEDS_BUSINESS_CAP"):
        _tx(amount_minor=-(2_000_000_000_000))


def test_f020_normal_amount_accepted():
    _tx(amount_minor=-1000)  # no raise


# ---- F021 AUTO_PROPOSE must not carry a warning --------------------------

def test_f021_auto_propose_with_warning_rejected():
    with pytest.raises(ClassificationContractError, match="AUTO_PROPOSE_HAS_WARNING"):
        _auto(warnings=(ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,))


def test_f021_clean_auto_propose_accepted():
    _auto()  # no raise


# ---- F022 regression detects rule/reason/confidence drift ----------------

def test_f022_rule_digest_change_is_regression():
    before = [_auto(rule_digest="a" * 64)]
    after = [_auto(rule_digest="b" * 64)]
    with pytest.raises(RegressionViolation, match="REGRESSION_AUTO_PROPOSAL_CHANGED"):
        prove_zero_regression(before, after)


def test_f022_confidence_change_is_regression():
    # confidence must be exactly 10000 for AUTO_PROPOSE, so drift is expressed via a review->auto
    before = [_auto()]
    after = [_auto(account_id="acc.other")]
    with pytest.raises(RegressionViolation, match="REGRESSION_AUTO_PROPOSAL_CHANGED"):
        prove_zero_regression(before, after)


def test_f022_identical_is_zero_regression():
    prove_zero_regression([_auto()], [_auto()])  # no raise
