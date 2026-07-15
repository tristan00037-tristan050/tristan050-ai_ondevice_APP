"""§6 — the stage-3 classification path runs end-to-end through the real Stage3Classifier and
emits a schema-bound decision receipt, and the stage-3 attack subset is executed with fail classes.

Journal/ledger/report and the full 40-attack matrix are 5·6단계 (DEFERRED_TO_STAGE5).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from butler_pc_core.accounting.classify.contracts import (
    ReasonRegistryError,
    build_decision_receipt,
    registry_closure_digest,
)
from butler_pc_core.accounting.classify.models import (
    ClassificationContractError,
    DecisionState,
    ReasonCode,
)
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier

from tests.accounting.classify.conftest import RecordingPort, make_transaction


def _classify(**port_kwargs):
    tx = make_transaction()
    draft = Stage3Classifier().classify(tx, RecordingPort(**port_kwargs))
    return tx, draft


# ---- E2E happy path: classify → bound receipt ---------------------------

def test_e2e_exact_rule_auto_proposes_and_receipt_binds_digests():
    tx, draft = _classify()
    assert draft.state is DecisionState.AUTO_PROPOSE
    receipt = build_decision_receipt(draft, tx)
    assert receipt["state"] == "AUTO_PROPOSE"
    assert receipt["reason_code"] == "AUTO_PROPOSE_EXACT_RULE"
    assert receipt["transaction_canonical_digest"] and len(receipt["transaction_canonical_digest"]) == 64
    assert receipt["reason_registry_closure_digest"] == registry_closure_digest()
    assert receipt["journal_auto_post_allowed"] is False  # stage-3 proposes only


def test_e2e_self_transfer_guard_runs_before_rule_selection():
    tx, draft = _classify(own_account=True)
    assert draft.state is DecisionState.REVIEW_REQUIRED
    assert draft.reason_code is ReasonCode.REVIEW_SELF_TRANSFER
    # guard first: rule selection must not have been consulted
    port = RecordingPort(own_account=True)
    Stage3Classifier().classify(make_transaction(), port)
    assert "select_rule" not in port.call_names


# ---- Stage-3 attacks: each is executed and its fail class recorded -------

@pytest.mark.parametrize(
    "attack,port_kwargs,tx_overrides,expect_error,marker",
    [
        # fake / non-boolean authority reply on ownership → fail closed
        ("fake_profile_binding", {"fail_on": "is_own_account"}, {}, "classify", "BLOCK_AUTHORITY_BINDING"),
        # forged transcript (semantic mismatch) → fail closed
        ("forged_transcript", {"invalid_transcript": True}, {}, "classify", "BLOCK"),
        # policy-digest / rule tamper: KRW exponent injected != 0 → currency block
        ("policy_exponent_inject", {"exponent": 2}, {}, "classify", "BLOCK_CURRENCY_EXPONENT"),
    ],
)
def test_stage3_attack_fail_classes(attack, port_kwargs, tx_overrides, expect_error, marker):
    tx = make_transaction(**tx_overrides)
    draft = Stage3Classifier().classify(tx, RecordingPort(**port_kwargs))
    # every attack must land in a BLOCKED/REVIEW draft (never a silent AUTO_PROPOSE)
    assert draft.state is not DecisionState.AUTO_PROPOSE
    assert draft.reason_code.value.startswith(marker) or draft.state is DecisionState.BLOCKED


def test_stage3_attack_datetime_in_date_field_rejected():
    with pytest.raises(ClassificationContractError, match="TRANSACTION_DATE_INVALID"):
        make_transaction(booked_date=datetime(2026, 7, 15))  # F019 at parse


def test_stage3_attack_out_of_range_amount_rejected():
    with pytest.raises(ClassificationContractError, match="AMOUNT_OUT_OF_RANGE_64BIT"):
        make_transaction(amount_minor=-(10**200))  # F020 at parse


def test_stage3_attack_out_of_registry_reason_rejected_by_receipt():
    tx, draft = _classify()
    receipt = build_decision_receipt(draft, tx)
    receipt["reason_code"] = "MADE_UP_REASON"  # forge an unregistered reason on the wire
    from butler_pc_core.accounting.classify.contracts import validate_decision_receipt
    with pytest.raises(ReasonRegistryError, match="DECISION_RECEIPT_SCHEMA_INVALID"):
        validate_decision_receipt(receipt)
