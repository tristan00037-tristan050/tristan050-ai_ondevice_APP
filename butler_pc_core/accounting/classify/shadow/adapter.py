"""Legacy bank row → PII-free CanonicalTransactionV2, and a deterministic policy port
backed by the committed atlink bundle. Observe-only; never posts a journal.

The port is faithful to the current policy maturity: the approved vendor-descriptor registry is
empty (status BLOCKED_EMPTY_REGISTRY), so every vendor resolves to NO_MATCH and the classifier
holds the transaction for review. If the registry is later finance-approved, exact matches will
surface as AUTO_PROPOSE without any code change here.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from butler_pc_core.accounting.classify.models import (
    BankDirection,
    CanonicalTransactionV2,
    EconomicEventKind,
)
from butler_pc_core.accounting.classify.port import (
    CurrencyExponentReply,
    RuleBasis,
    RuleFacts,
    RuleSelectionReply,
    VendorMatchReply,
    VendorMatchState,
)
from butler_pc_core.accounting.classify.shadow.record import digest_text

_BUNDLE = (
    Path(__file__).resolve().parents[2]  # …/accounting
    / "policy" / "bundles" / "atlink_smb_v2_1_draft"
)
_SHADOW_TENANT = "shadow-observe"
_SHADOW_COMPANY = "shadow-observe"
_SHADOW_BANK = "shadow-bank"
_CURRENCY_REGISTRY_VERSION = "atlink-krw-v1"
_DESCRIPTOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HMAC_RE = re.compile(r"^[0-9a-f]{64}$")
_ACCOUNTING_DIRECTION = {
    BankDirection.OUTFLOW: "DEBIT",
    BankDirection.INFLOW: "CREDIT",
}


def _tok(text: object) -> str | None:
    """PII-free synthetic token (tok_<32 hex>) from a hash, or None for empty."""
    s = str(text if text is not None else "").strip()
    if not s:
        return None
    return "tok_" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:40]


def build_canonical_transaction(
    *,
    index: int,
    amount_minor: int,
    booked_date: date,
    value_date: date,
    desc_text: object = "",
    vendor_text: object = "",
    counterparty_text: object = "",
) -> CanonicalTransactionV2:
    """Build a non-PII canonical view. Raw memo/vendor/counterparty are only ever hashed."""
    direction = BankDirection.OUTFLOW if amount_minor < 0 else BankDirection.INFLOW
    row_digest = hashlib.sha256(
        f"{index}|{amount_minor}|{booked_date.isoformat()}|{digest_text(desc_text)}".encode("utf-8")
    ).hexdigest()
    feature = digest_text(f"{desc_text}|{vendor_text}")
    return CanonicalTransactionV2(
        tenant_id=_SHADOW_TENANT,
        company_id=_SHADOW_COMPANY,
        request_id=f"shadow-{index:08d}",
        transaction_id=f"shadow-tx-{index:08d}",
        source_bank_id=_SHADOW_BANK,
        booked_date=booked_date,
        value_date=value_date,
        direction=direction,
        amount_minor=amount_minor,
        currency="KRW",
        currency_registry_version=_CURRENCY_REGISTRY_VERSION,
        transaction_digest=row_digest,
        source_record_digest=row_digest,
        counterparty_account_token=_tok(counterparty_text),
        vendor_token=_tok(vendor_text),
        description_feature_digests=(feature,),
        evidence_digests=(feature,),
    )


def transaction_key(tx: CanonicalTransactionV2) -> str:
    """Anonymous stable key for the comparison record (never a real id)."""
    return tx.transaction_digest


class AtlinkShadowPort:
    """Deterministic PolicyPort over the committed atlink bundle. No network, no PII."""

    def __init__(self) -> None:
        self._chart_ids = self._load_chart_ids()
        self._approved_vendors = self._load_approved_vendors()
        self._rules = self._load_rules()
        self._calls: list[str] = []

    @staticmethod
    def _read(rel: str) -> dict[str, Any]:
        return json.loads((_BUNDLE / rel).read_text(encoding="utf-8"))

    def _load_chart_ids(self) -> frozenset[str]:
        chart = self._read("upstream/chart_of_accounts.atlink.v1.json")
        accs = chart.get("accounts") or []
        return frozenset(a["account_id"] for a in accs if isinstance(a, dict) and a.get("account_id"))

    def _load_approved_vendors(self) -> dict[str, str]:
        reg = self._read("vendor_descriptor_registry.template.json")
        # Only APPROVED (non-empty) registries contribute matches. Currently BLOCKED_EMPTY_REGISTRY.
        if (
            str(reg.get("status", "")).upper() != "APPROVED"
            or not isinstance(reg.get("approval_id"), str)
            or not str(reg["approval_id"]).strip()
        ):
            return {}
        out: dict[str, str] = {}
        for d in reg.get("descriptors") or []:
            if not isinstance(d, dict):
                continue
            token = d.get("normalized_exact_value_hmac")
            match_id = d.get("descriptor_id")
            if (
                not isinstance(token, str)
                or not _HMAC_RE.fullmatch(token)
                or not isinstance(match_id, str)
                or not _DESCRIPTOR_ID_RE.fullmatch(match_id)
            ):
                continue
            previous = out.get(token)
            if previous is not None and previous != match_id:
                raise ValueError("VENDOR_DESCRIPTOR_HMAC_CONFLICT")
            out[token] = match_id
        return out

    def _load_rules(self) -> list[dict[str, Any]]:
        rules = self._read("upstream/account_mapping_rules.v1.json").get("rules") or []
        return [r for r in rules if isinstance(r, dict)]

    # --- PolicyPort protocol -------------------------------------------------
    def currency_exponent(self, currency: str, registry_version: str) -> CurrencyExponentReply:
        self._calls.append(f"cx:{currency}:{registry_version}")
        return CurrencyExponentReply(0)  # KRW bank statements

    def is_own_account(self, counterparty_account_token: str | None) -> bool:
        # Shadow has no verified company own-account registry → conservative (never asserts own).
        self._calls.append(f"own:{counterparty_account_token or '-'}")
        return False

    def match_vendor_exact(self, vendor_token: str | None) -> VendorMatchReply:
        self._calls.append(f"vendor:{vendor_token or '-'}")
        match_id = self._approved_vendors.get(str(vendor_token)) if vendor_token else None
        if match_id is None:
            return VendorMatchReply(VendorMatchState.NO_MATCH)
        return VendorMatchReply(VendorMatchState.EXACT, match_id)

    def select_rule(self, facts: RuleFacts) -> RuleSelectionReply:
        self._calls.append(f"rule:{facts.vendor_match_id or '-'}:{facts.direction.value}")
        # Rules require an approved vendor-descriptor exact match. Without one → NO_MATCH (review).
        if facts.vendor_match_id is None:
            return RuleSelectionReply(RuleBasis.NO_MATCH)
        expected_direction = _ACCOUNTING_DIRECTION[facts.direction]
        for rule in self._rules:
            acct = rule.get("target_account_id")
            rule_direction = (
                str(rule.get("bank_direction", ""))
                if "bank_direction" in rule
                else str(rule.get("direction", ""))
            )
            direction_matches = (
                rule_direction == facts.direction.value
                if "bank_direction" in rule
                else rule_direction == expected_direction
            )
            if acct in self._chart_ids and direction_matches:
                rule_id = str(rule.get("rule_id"))
                rdigest = hashlib.sha256(
                    json.dumps(rule, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                return RuleSelectionReply(
                    RuleBasis.EXACT_DETERMINISTIC, account_id=acct, rule_id=rule_id,
                    rule_digest=rdigest, score_bp=10_000, evidence_complete=True,
                )
        return RuleSelectionReply(RuleBasis.NO_MATCH)

    def is_known_account(self, account_id: str) -> bool:
        self._calls.append(f"known:{account_id}")
        return account_id in self._chart_ids

    def transcript_digest(self) -> str:
        return hashlib.sha256("\n".join(self._calls).encode("utf-8")).hexdigest()
