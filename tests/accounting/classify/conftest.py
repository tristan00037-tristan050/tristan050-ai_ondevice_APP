from __future__ import annotations

from datetime import date

import pytest

from butler_pc_core.accounting.classify.models import (
    BankDirection,
    CanonicalTransactionV2,
    ReasonCode,
    stable_digest,
)
from butler_pc_core.accounting.classify.port import (
    CurrencyExponentReply,
    PolicyPortError,
    RuleBasis,
    RuleFacts,
    RuleSelectionReply,
    VendorMatchReply,
    VendorMatchState,
)


def digest(label: str) -> str:
    return stable_digest({"synthetic_label": label})


def make_transaction(**overrides) -> CanonicalTransactionV2:
    values = {
        "tenant_id": "tenant-stage3",
        "company_id": "company-stage3",
        "request_id": "request-stage3-001",
        "transaction_id": "txn-stage3-001",
        "source_bank_id": "bank-synthetic",
        "booked_date": date(2026, 7, 15),
        "value_date": date(2026, 7, 15),
        "direction": BankDirection.OUTFLOW,
        "amount_minor": -125_000,
        "currency": "KRW",
        "currency_registry_version": "currency-registry-v1",
        "transaction_digest": digest("transaction-001"),
        "source_record_digest": digest("source-001"),
        "counterparty_account_token": "tok_account_0123456789abcdef",
        "vendor_token": "tok_vendor_0123456789abcdef",
        "purpose_code": "EXTERNAL_MARKETING",
        "purpose_evidence_digest": digest("purpose-001"),
        "description_feature_digests": (digest("feature-001"),),
        "evidence_digests": (digest("evidence-001"),),
    }
    values.update(overrides)
    return CanonicalTransactionV2(**values)


class RecordingPort:
    """Deterministic unit-test transport; deliberately has no receipt/signature API."""

    def __init__(
        self,
        *,
        exponent: int = 0,
        own_account: bool = False,
        vendor: VendorMatchReply | None = None,
        selection: RuleSelectionReply | None = None,
        known_account: bool = True,
        fail_on: str | None = None,
        invalid_transcript: bool = False,
    ) -> None:
        self.exponent = exponent
        self.own_account = own_account
        self.vendor = vendor or VendorMatchReply(VendorMatchState.EXACT, "match.vendor.synthetic")
        self.selection = selection or exact_selection()
        self.known_account = known_account
        self.fail_on = fail_on
        self.invalid_transcript = invalid_transcript
        self.calls: list[tuple[str, str]] = []

    @property
    def call_names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def _record(self, name: str, payload: object) -> None:
        if self.fail_on == name:
            raise PolicyPortError(ReasonCode.BLOCK_AUTHORITY_BINDING)
        self.calls.append((name, stable_digest(payload)))

    def currency_exponent(self, currency: str, registry_version: str) -> CurrencyExponentReply:
        self._record("currency_exponent", {"currency": currency, "registry_version": registry_version})
        return CurrencyExponentReply(self.exponent)

    def is_own_account(self, counterparty_account_token: str | None) -> bool:
        self._record("is_own_account", {"token_digest": stable_digest(counterparty_account_token)})
        return self.own_account

    def match_vendor_exact(self, vendor_token: str | None) -> VendorMatchReply:
        self._record("match_vendor_exact", {"token_digest": stable_digest(vendor_token)})
        return self.vendor

    def select_rule(self, facts: RuleFacts) -> RuleSelectionReply:
        self._record(
            "select_rule",
            {
                "direction": facts.direction.value,
                "event_kind": facts.event_kind.value,
                "vendor_match_id": facts.vendor_match_id,
                "purpose_code": facts.purpose_code,
                "evidence_count": len(facts.evidence_digests),
            },
        )
        return self.selection

    def is_known_account(self, account_id: str) -> bool:
        self._record("is_known_account", {"account_id": account_id})
        return self.known_account

    def transcript_digest(self) -> str:
        self._record("transcript_digest", {"prior_query_count": len(self.calls)})
        if self.invalid_transcript:
            return "invalid"
        return stable_digest(self.calls)


def exact_selection() -> RuleSelectionReply:
    return RuleSelectionReply(
        basis=RuleBasis.EXACT_DETERMINISTIC,
        account_id="PL.SGA.ADVERTISING",
        rule_id="MAP-SAAS-ADVERTISING",
        rule_digest=digest("rule-advertising"),
        score_bp=10_000,
        evidence_complete=True,
    )


@pytest.fixture
def transaction() -> CanonicalTransactionV2:
    return make_transaction()


@pytest.fixture
def port() -> RecordingPort:
    return RecordingPort()
