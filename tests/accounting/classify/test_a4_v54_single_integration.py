from __future__ import annotations

import hashlib
import base64
import uuid
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from butler_pc_core.a4_verifier.cli import (
    Block,
    _token,
    canonical_evidence_value,
    rebuild_edges,
    terminal_partition,
)
from butler_pc_core.a4_verifier.canonical import receipt_signing_bytes
from butler_pc_core.accounting.assignment.security import MemoryKeyStore, TokenService
from butler_pc_core.accounting.classify.reconciliation_v2 import (
    A4ContractError,
    CompiledTransaction,
    CounterpartyResolution,
    Direction,
    FxRule,
    MatchType,
    VerifiedPolicy,
    reconcile,
    jcs_bytes,
)
from butler_pc_core.accounting.classify.verifier_authority import (
    VerifierAuthorityTrust,
    load_authority_trust,
    verify_authority_receipt_signature,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


TENANT = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
ACCOUNT_A = str(uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
ACCOUNT_B = str(uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))
NOW = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def test_verifier_evidence_token_matches_product_nfkc_whitespace_contract():
    raw_reference = "  ＡＢＣ　   １２３  "
    token_service = TokenService(MemoryKeyStore(key=b"K" * 32))

    _, product_token = token_service.a4_evidence_token(
        TENANT, "BANK_REFERENCE", raw_reference
    )
    material = token_service.a4_verifier_material(TENANT)
    verifier_key = base64.urlsafe_b64decode(material["bank_reference_key_b64"])
    verifier_token = _token(
        verifier_key,
        TENANT,
        "BANK_REFERENCE",
        canonical_evidence_value(raw_reference),
    )

    assert canonical_evidence_value(raw_reference) == "ABC 123"
    assert verifier_token == product_token


def _tx(
    name: str,
    *,
    direction: Direction,
    amount: int,
    currency: str = "KRW",
) -> CompiledTransaction:
    source, target = (
        (ACCOUNT_A, ACCOUNT_B)
        if direction is Direction.OUTFLOW
        else (ACCOUNT_B, ACCOUNT_A)
    )
    return CompiledTransaction(
        tenant_id=TENANT,
        txn_uid=str(uuid.uuid5(uuid.NAMESPACE_URL, f"a4-v54:{name}")),
        source_row_digest=_digest(f"row:{name}"),
        row_ordinal=int(_digest(name)[:6], 16),
        canonical_row_digest=_digest(f"canonical:{name}"),
        source_account_id=source,
        direction=direction,
        amount_minor=amount,
        currency=currency,
        booked_at_utc=NOW,
        local_date=date(2026, 7, 21),
        artifact_token=_digest(f"artifact:{name}")[:32],
        bank_code="BANK",
        bank_reference_token=_digest("shared-reference"),
        counterparty_account_token=_digest(f"counterparty:{name}")[:32],
        resolved_counterparty_account_id=target,
        counterparty_resolution=CounterpartyResolution.EXACT_VERIFIED,
        row_kind="PRINCIPAL",
        product_code_id="DEFAULT",
        channel_id="DEFAULT",
    )


def _policy(*, fx_rules: tuple[FxRule, ...] = (), branch_cap: int = 4_096) -> VerifiedPolicy:
    return VerifiedPolicy(
        {},
        {},
        0,
        1,
        20,
        10_000,
        (),
        max_subset_size=8,
        max_subset_branches=branch_cap,
        fx_rules=fx_rules,
    )


def _policy_payload(*, fx_rules: list[dict[str, object]] | None = None, branch_cap: int = 4_096) -> dict[str, object]:
    return {
        "min_signed_gap_days": 0,
        "max_signed_gap_days": 1,
        "max_component_nodes": 20,
        "max_candidate_edges": 10_000,
        "max_transactions": 100_000,
        "max_pair_checks": 250_000,
        "max_trace_bucket": 10_000,
        "max_memory_bytes": 512 * 1024 * 1024,
        "max_subset_size": 8,
        "max_subset_branches": branch_cap,
        "fee_rules": [],
        "fx_rules": fx_rules or [],
    }


@pytest.mark.parametrize(
    "transactions",
    [
        (
            _tx("one-out", direction=Direction.OUTFLOW, amount=100),
            _tx("many-in-40", direction=Direction.INFLOW, amount=40),
            _tx("many-in-60", direction=Direction.INFLOW, amount=60),
        ),
        (
            _tx("many-out-40", direction=Direction.OUTFLOW, amount=40),
            _tx("many-out-60", direction=Direction.OUTFLOW, amount=60),
            _tx("one-in", direction=Direction.INFLOW, amount=100),
        ),
    ],
)
def test_product_and_independent_verifier_agree_on_bounded_partial_edges(transactions):
    result = reconcile(transactions, _policy())
    assert len(result.forced_edges) == 1
    assert result.forced_edges[0].match_type is MatchType.PARTIAL
    assert result.forced_edges[0].principal_count == 3
    observed = [edge.safe_dict() for edge in result.edges]
    rebuilt, pair_checks, _bucket, branches = rebuild_edges(
        [tx.safe_dict() for tx in transactions], _policy_payload()
    )
    assert rebuilt == observed
    assert pair_checks == 0
    assert branches == result.candidate_subset_branches == 1


def test_fx_requires_receipt_bound_exact_rational_fee_and_spread_conservation():
    outflow = _tx("fx-out", direction=Direction.OUTFLOW, amount=10_000, currency="USD")
    inflow = _tx("fx-in", direction=Direction.INFLOW, amount=19_600, currency="EUR")
    rule = FxRule(
        "FX-USD-EUR-20260721",
        "USD",
        "EUR",
        200,
        100,
        100,
        2,
        100,
        "EXACT_RATIONAL",
        datetime(2026, 7, 21, tzinfo=timezone.utc),
        datetime(2026, 7, 22, tzinfo=timezone.utc),
        "d" * 64,
    )
    assert reconcile((outflow, inflow), _policy()).edges == ()
    result = reconcile((outflow, inflow), _policy(fx_rules=(rule,)))
    assert len(result.forced_edges) == 1
    edge = result.forced_edges[0]
    assert edge.match_type is MatchType.FX
    assert edge.fx_receipt_digest == "d" * 64
    rule_payload = {
        "rule_id": rule.rule_id,
        "from_currency": rule.from_currency,
        "to_currency": rule.to_currency,
        "rate_numerator": rule.rate_numerator,
        "rate_denominator": rule.rate_denominator,
        "source_fee_minor": rule.source_fee_minor,
        "target_fee_minor": rule.target_fee_minor,
        "spread_bps": rule.spread_bps,
        "rounding_mode": rule.rounding_mode,
        "effective_from": "2026-07-21T00:00:00Z",
        "effective_to": "2026-07-22T00:00:00Z",
        "rate_source_receipt_digest": rule.rate_source_receipt_digest,
    }
    rebuilt, *_ = rebuild_edges(
        [outflow.safe_dict(), inflow.safe_dict()],
        _policy_payload(fx_rules=[rule_payload]),
    )
    assert rebuilt == [edge.safe_dict()]


def test_subset_search_blocks_instead_of_returning_partial_results():
    transactions = (
        _tx("cap-out", direction=Direction.OUTFLOW, amount=100),
        _tx("cap-in-1", direction=Direction.INFLOW, amount=20),
        _tx("cap-in-2", direction=Direction.INFLOW, amount=30),
        _tx("cap-in-3", direction=Direction.INFLOW, amount=50),
    )
    with pytest.raises(A4ContractError, match="BLOCK_RESOURCE_SUBSET_BRANCHES"):
        reconcile(transactions, _policy(branch_cap=1))
    with pytest.raises(Block, match="BLOCK_RESOURCE_SUBSET_BRANCHES"):
        rebuild_edges(
            [tx.safe_dict() for tx in transactions],
            _policy_payload(branch_cap=1),
        )


def test_value_date_controls_pairing_without_mutating_booking_evidence():
    outflow = replace(
        _tx("value-out", direction=Direction.OUTFLOW, amount=100),
        local_date=date(2026, 7, 1),
        value_date=date(2026, 7, 21),
    )
    inflow = replace(
        _tx("value-in", direction=Direction.INFLOW, amount=100),
        local_date=date(2026, 7, 30),
        value_date=date(2026, 7, 21),
    )
    result = reconcile((outflow, inflow), _policy())
    assert len(result.forced_edges) == 1
    rebuilt, *_ = rebuild_edges(
        [outflow.safe_dict(), inflow.safe_dict()], _policy_payload()
    )
    assert rebuilt == [result.forced_edges[0].safe_dict()]


def test_duplicate_and_reversal_are_terminal_once_and_verifier_agrees():
    original_reference = _digest("original-reference")
    original = replace(
        _tx("original", direction=Direction.OUTFLOW, amount=100),
        bank_reference_token=original_reference,
    )
    reversal = replace(
        _tx("reversal", direction=Direction.INFLOW, amount=100),
        source_account_id=ACCOUNT_A,
        resolved_counterparty_account_id=ACCOUNT_B,
        bank_reference_token=_digest("reversal-reference"),
        reversal_of_reference_token=original_reference,
    )
    duplicate = replace(
        _tx("duplicate", direction=Direction.OUTFLOW, amount=100),
        bank_reference_token=_digest("duplicate-reference"),
        duplicate_of_reference_token=original_reference,
    )
    pair = (
        _tx("active-out", direction=Direction.OUTFLOW, amount=55),
        _tx("active-in", direction=Direction.INFLOW, amount=55),
    )
    transactions = (original, reversal, duplicate, *pair)
    result = reconcile(transactions, _policy())
    assert len(result.forced_edges) == 1
    assert {uid for group in result.terminal_groups for uid in group.transaction_uids} == {
        original.txn_uid,
        reversal.txn_uid,
        duplicate.txn_uid,
    }
    assert len(result.terminal_groups) == 2
    active, terminal = terminal_partition([tx.safe_dict() for tx in transactions])
    assert terminal == [group.safe_dict() for group in result.terminal_groups]
    rebuilt, *_ = rebuild_edges(active, _policy_payload())
    assert rebuilt == [result.forced_edges[0].safe_dict()]


def test_overlapping_terminal_ownership_fails_closed():
    original_reference = _digest("overlap-original")
    duplicate_reference = _digest("overlap-duplicate")
    original = replace(
        _tx("overlap-original", direction=Direction.OUTFLOW, amount=100),
        bank_reference_token=original_reference,
    )
    duplicate = replace(
        _tx("overlap-duplicate", direction=Direction.OUTFLOW, amount=100),
        bank_reference_token=duplicate_reference,
        duplicate_of_reference_token=original_reference,
    )
    reversal = replace(
        _tx("overlap-reversal", direction=Direction.INFLOW, amount=100),
        source_account_id=ACCOUNT_A,
        resolved_counterparty_account_id=ACCOUNT_B,
        reversal_of_reference_token=duplicate_reference,
    )
    with pytest.raises(A4ContractError, match="BLOCK_DUPLICATE_BINDING"):
        reconcile((original, duplicate, reversal), _policy())
    with pytest.raises(Block, match="BLOCK_DUPLICATE_BINDING"):
        terminal_partition(
            [tx.safe_dict() for tx in (original, duplicate, reversal)]
        )


@pytest.mark.parametrize("bad_cdhash", ["0" * 64, "f" * 64])
def test_active_authority_trust_rejects_placeholder_cdhashes(tmp_path, bad_cdhash):
    private = Ed25519PrivateKey.generate()
    trust = {
        "schema_version": "butler.box5.a4.verifier_authority_trust.v5.3",
        "enabled": True,
        "environment": "TEST",
        "authority_id": "butler-a4-test-authority",
        "transport": "native-xpc-v5.3",
        "algorithm": "Ed25519",
        "signer_key_id": "butler-a4-test-key",
        "public_key_b64": base64.b64encode(
            private.public_key().public_bytes_raw()
        ).decode("ascii"),
        "key_epoch": 1,
        "minimum_key_epoch": 1,
        "revoked_key_ids": [],
        "not_before_utc": "2026-01-01T00:00:00Z",
        "not_after_utc": "2027-01-01T00:00:00Z",
        "expected_authority_cdhash": bad_cdhash,
        "expected_verifier_cdhash": "b" * 64,
    }
    path = tmp_path / "trust.json"
    path.write_bytes(jcs_bytes(trust))
    path.chmod(0o600)
    with pytest.raises(A4ContractError, match="BLOCK_TRUST_POLICY"):
        load_authority_trust(
            path,
            now=datetime(2026, 7, 21, tzinfo=timezone.utc),
            allow_test_authority=True,
        )


def test_signed_receipt_with_mismatched_binary_identity_is_rejected():
    private = Ed25519PrivateKey.generate()
    trust = VerifierAuthorityTrust(
        authority_id="butler-a4-test-authority",
        signer_key_id="butler-a4-test-key",
        public_key=private.public_key().public_bytes_raw(),
        key_epoch=1,
        trust_digest="c" * 64,
        environment="TEST",
        not_before=datetime(2026, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2027, 1, 1, tzinfo=timezone.utc),
        minimum_key_epoch=1,
        revoked_key_ids=frozenset(),
        expected_authority_cdhash="a" * 64,
        expected_verifier_cdhash="b" * 64,
    )
    receipt = {
        "schema_version": "butler.box5.a4.verification_receipt.v5.3",
        "contract_id": "BUTLER-BOX5-A4-V5.3-NATIVE-AUTHORITY",
        "protocol_version": "butler.box5.a4.authority_protocol.v5.3",
        "authority_id": trust.authority_id,
        "signer_key_id": trust.signer_key_id,
        "signer_key_epoch": trust.key_epoch,
        "signer_trust_digest": trust.trust_digest,
        "authority_cdhash": "d" * 64,
        "verifier_cdhash": trust.expected_verifier_cdhash,
    }
    receipt["signature"] = base64.urlsafe_b64encode(
        private.sign(receipt_signing_bytes(receipt))
    ).decode("ascii").rstrip("=")
    with pytest.raises(A4ContractError, match="BLOCK_SIGNATURE"):
        verify_authority_receipt_signature(receipt, trust)
