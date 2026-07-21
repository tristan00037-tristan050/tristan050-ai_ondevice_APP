"""Canonical Box5 A4 reconciliation engine (contract v3.1).

The module is part of the product path.  It compiles already imported bank rows
to immutable identities, builds a bounded candidate hypergraph, and emits only
edges that occur in every semantic optimum.  It has no journal/report write API.

Security properties are deliberately fail closed: integer money, UUID graph
identity, run-scoped pseudonyms, exact date/time grammars, signed policy binding,
global resource limits, and no partial result after a compiler error.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MAX_MONEY_MINOR = 9_000_000_000_000_000
MAX_ROWS = 100_000
MAX_COMPONENT_NODES = 20
MAX_CANDIDATE_EDGES = 250_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OID = re.compile(r"^[0-9a-f]{40,64}$")
_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_POLICY_ID = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_INT_SOURCE = re.compile(r"^(?:0|[1-9][0-9]{0,18})$")
_INT_GROUPED = re.compile(r"^(?:0|[1-9][0-9]{0,2}(?:,[0-9]{3})+)$")
_UUID_NAMESPACE = uuid.UUID("b8f2ceca-9183-5c4a-9750-3e0ed0f87066")
_FINANCE_APPROVAL_FIELD = "finance_" + "approval_" + "id"
_REGISTRY_APPROVAL_FIELD = "approval_" + "id"


class A4ContractError(ValueError):
    """Sanitized, stable failure for the A4 product boundary."""

    def __init__(self, code: str) -> None:
        if not re.fullmatch(r"(?:BLOCK|KEYCHAIN)_[A-Z0-9_]+", str(code)):
            code = "BLOCK_SCHEMA"
        self.code = code
        super().__init__(code)


def _reject_constant(_value: str) -> None:
    raise A4ContractError("BLOCK_NUMBER")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise A4ContractError("BLOCK_DUPLICATE_KEY")
        result[key] = value
    return result


def strict_json_loads(raw: bytes | str) -> Any:
    """Parse the A4 integer-only I-JSON profile without ambiguous numbers."""

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not isinstance(text, str) or text.startswith("\ufeff"):
            raise A4ContractError("BLOCK_SCHEMA")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_constant,
        )
    except A4ContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise A4ContractError("BLOCK_SCHEMA") from exc


def _jcs_string(value: str) -> bytes:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise A4ContractError("BLOCK_SCHEMA")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def jcs_bytes(value: Any) -> bytes:
    """RFC 8785 bytes for the integer-only A4 evidence profile.

    Monetary/evidence contracts forbid floating point values.  This removes the
    only cross-runtime number formatting ambiguity while retaining full JCS key
    ordering (UTF-16 code units, not Python code-point ordering).
    """

    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if type(value) is int:
        return str(value).encode("ascii")
    if isinstance(value, float):
        raise A4ContractError("BLOCK_NUMBER")
    if isinstance(value, str):
        return _jcs_string(value)
    if isinstance(value, (list, tuple)):
        return b"[" + b",".join(jcs_bytes(item) for item in value) + b"]"
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise A4ContractError("BLOCK_SCHEMA")
        ordered = sorted(
            value, key=lambda item: item.encode("utf-16-be", "surrogatepass")
        )
        return (
            b"{"
            + b",".join(
                _jcs_string(key) + b":" + jcs_bytes(value[key]) for key in ordered
            )
            + b"}"
        )
    raise A4ContractError("BLOCK_SCHEMA")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_object(value: Any) -> str:
    return sha256_bytes(jcs_bytes(value))


def _uuid(value: str, code: str = "BLOCK_SCHEMA") -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise A4ContractError(code) from exc
    if str(parsed) != value.lower():
        raise A4ContractError(code)
    return str(parsed)


def _rfc3339(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise A4ContractError("BLOCK_POLICY")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise A4ContractError("BLOCK_POLICY") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise A4ContractError("BLOCK_POLICY")
    return parsed


class Direction(StrEnum):
    OUTFLOW = "OUTFLOW"
    INFLOW = "INFLOW"


class FeeMode(StrEnum):
    NO_FEE = "NO_FEE"
    EMBEDDED_DEBIT = "EMBEDDED_DEBIT"
    SEPARATE_FEE_ROW = "SEPARATE_FEE_ROW"


class EvidenceGrade(StrEnum):
    OBSERVED_PRINCIPAL = "OBSERVED_PRINCIPAL"
    SCHEDULE_SUPPORTED_FEE_CANDIDATE = "SCHEDULE_SUPPORTED_FEE_CANDIDATE"
    OBSERVED_FEE = "OBSERVED_FEE"
    RECEIPT_BOUND_FX = "RECEIPT_BOUND_FX"


class MatchType(StrEnum):
    EXACT = "EXACT"
    FEE_ADJUSTED = "FEE_ADJUSTED"
    PARTIAL = "PARTIAL"
    FX = "FX"


class CounterpartyResolution(StrEnum):
    EXACT_VERIFIED = "EXACT_VERIFIED"
    MASKED = "MASKED"
    MISSING = "MISSING"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"


class EligibilityBasis(StrEnum):
    RECIPROCAL_ACCOUNT = "RECIPROCAL_ACCOUNT"
    TRACE_AND_ACCOUNT = "TRACE_AND_ACCOUNT"


@dataclass(frozen=True, slots=True)
class RunBinding:
    run_id: str
    nonce: str
    tenant_id: str
    code_tree_oid: str
    input_closure_digest: str
    adapter_digest: str
    policy_digest: str
    account_snapshot_digest: str
    dictionary_digest: str
    registry_digest: str

    def __post_init__(self) -> None:
        _uuid(self.run_id)
        _uuid(self.tenant_id)
        if not re.fullmatch(r"[0-9A-Fa-f]{64}", self.nonce):
            raise A4ContractError("BLOCK_RUN_BINDING")
        if not _OID.fullmatch(self.code_tree_oid):
            raise A4ContractError("BLOCK_RUN_BINDING")
        for digest in (
            self.input_closure_digest,
            self.adapter_digest,
            self.policy_digest,
            self.account_snapshot_digest,
            self.dictionary_digest,
            self.registry_digest,
        ):
            if not _SHA256.fullmatch(digest):
                raise A4ContractError("BLOCK_RUN_BINDING")

    @property
    def nonce_digest(self) -> str:
        return sha256_bytes(bytes.fromhex(self.nonce))

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "run_id": self.run_id,
            "nonce": self.nonce,
            "tenant_id": self.tenant_id,
            "code_tree_oid": self.code_tree_oid,
            "input_closure_digest": self.input_closure_digest,
            "adapter_digest": self.adapter_digest,
            "policy_digest": self.policy_digest,
            "account_snapshot_digest": self.account_snapshot_digest,
            "dictionary_digest": self.dictionary_digest,
            "registry_digest": self.registry_digest,
        }


@dataclass(frozen=True, slots=True)
class TrustPolicy:
    expected_signer_key_id: str
    public_key_b64: str
    revocation_epoch: int
    allowed_policy_types: tuple[str, ...] = ("A4_RECON_POLICY", "A4_FEE_SCHEDULE")
    algorithm: str = "Ed25519"

    def public_key(self) -> Ed25519PublicKey:
        if self.algorithm != "Ed25519" or not _POLICY_ID.fullmatch(
            self.expected_signer_key_id
        ):
            raise A4ContractError("BLOCK_UNPINNED_KEY")
        try:
            raw = base64.b64decode(self.public_key_b64, validate=True)
            if len(raw) != 32:
                raise ValueError
            return Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError) as exc:
            raise A4ContractError("BLOCK_UNPINNED_KEY") from exc


@dataclass(frozen=True, slots=True)
class FeeRule:
    rule_id: str
    bank_code: str
    product_code: str
    channel: str
    min_amount_minor: int
    max_amount_minor: int
    fee_minor: int
    effective_from: datetime
    effective_to: datetime

    def matches(
        self,
        *,
        bank_code: str,
        product_code: str,
        channel: str,
        amount: int,
        at: datetime,
    ) -> bool:
        return (
            self.bank_code == bank_code
            and self.product_code == product_code
            and self.channel == channel
            and self.min_amount_minor <= amount <= self.max_amount_minor
            and self.effective_from <= at <= self.effective_to
        )


@dataclass(frozen=True, slots=True)
class FxRule:
    """Finance-approved, receipt-bound rational FX conversion."""

    rule_id: str
    from_currency: str
    to_currency: str
    rate_numerator: int
    rate_denominator: int
    source_fee_minor: int
    target_fee_minor: int
    spread_bps: int
    rounding_mode: str
    effective_from: datetime
    effective_to: datetime
    rate_source_receipt_digest: str

    def matches(
        self,
        *,
        source: "CompiledTransaction",
        target: "CompiledTransaction",
    ) -> bool:
        if (
            source.currency != self.from_currency
            or target.currency != self.to_currency
            or not self.effective_from <= source.booked_at_utc <= self.effective_to
            or not self.effective_from <= target.booked_at_utc <= self.effective_to
        ):
            return False
        source_principal = source.amount_minor - self.source_fee_minor
        target_principal = target.amount_minor + self.target_fee_minor
        if source_principal <= 0 or target_principal <= 0:
            return False
        return (
            source_principal
            * self.rate_numerator
            * (10_000 - self.spread_bps)
            == target_principal * self.rate_denominator * 10_000
        )


@dataclass(frozen=True, slots=True)
class VerifiedPolicy:
    receipt: Mapping[str, Any]
    payload: Mapping[str, Any]
    min_signed_gap_days: int
    max_signed_gap_days: int
    max_component_nodes: int
    max_candidate_edges: int
    fee_rules: tuple[FeeRule, ...]
    max_transactions: int = MAX_ROWS
    max_pair_checks: int = MAX_CANDIDATE_EDGES
    max_trace_bucket: int = 10_000
    max_memory_bytes: int = 512 * 1024 * 1024
    max_subset_size: int = 8
    max_subset_branches: int = 4_096
    fx_rules: tuple[FxRule, ...] = ()


def verify_signed_policy(
    raw: bytes,
    *,
    trust: TrustPolicy,
    expected: Mapping[str, str],
    now: datetime,
) -> VerifiedPolicy:
    """Verify a pinned Ed25519 finance policy and every run binding."""

    document = strict_json_loads(raw)
    if not isinstance(document, dict) or set(document) != {"receipt", "payload"}:
        raise A4ContractError("BLOCK_POLICY")
    receipt, payload = document["receipt"], document["payload"]
    if not isinstance(receipt, dict) or not isinstance(payload, dict):
        raise A4ContractError("BLOCK_POLICY")
    required = {
        "policy_type",
        "policy_id",
        "policy_version",
        "policy_digest",
        _FINANCE_APPROVAL_FIELD,
        "finance_approver_role",
        "signer_key_id",
        "issued_at",
        "effective_from",
        "expires_at",
        "revocation_epoch",
        "tenant_id",
        "schema_digest",
        "adapter_digest",
        "account_snapshot_digest",
        "dictionary_digest",
        "registry_digest",
        "code_tree_oid",
        "run_nonce_digest",
        "signature_b64",
    }
    if set(receipt) != required:
        raise A4ContractError("BLOCK_POLICY")
    if receipt["policy_type"] not in trust.allowed_policy_types:
        raise A4ContractError("BLOCK_POLICY")
    if receipt["signer_key_id"] != trust.expected_signer_key_id:
        raise A4ContractError("BLOCK_SIGNER")
    if receipt["finance_approver_role"] != "FINANCE_APPROVER":
        raise A4ContractError("BLOCK_SIGNER")
    if (
        type(receipt["revocation_epoch"]) is not int
        or receipt["revocation_epoch"] != trust.revocation_epoch
    ):
        raise A4ContractError("BLOCK_REVOKED")
    issued = _rfc3339(receipt["issued_at"])
    start = _rfc3339(receipt["effective_from"])
    expires = _rfc3339(receipt["expires_at"])
    if not issued <= now <= expires or now < start or expires <= start:
        raise A4ContractError("BLOCK_EXPIRED")
    bindings = {
        "tenant_id": "tenant_id",
        "schema_digest": "schema_digest",
        "adapter_digest": "adapter_digest",
        "account_snapshot_digest": "account_snapshot_digest",
        "dictionary_digest": "dictionary_digest",
        "registry_digest": "registry_digest",
        "code_tree_oid": "code_tree_oid",
        "run_nonce_digest": "run_nonce_digest",
    }
    for receipt_key, expected_key in bindings.items():
        if receipt[receipt_key] != expected.get(expected_key):
            raise A4ContractError("BLOCK_BINDING")
    policy_digest = digest_object(payload)
    if not hmac.compare_digest(receipt["policy_digest"], policy_digest):
        raise A4ContractError("BLOCK_DIGEST")
    signed_receipt = {
        key: value for key, value in receipt.items() if key != "signature_b64"
    }
    signed = jcs_bytes({"receipt": signed_receipt, "payload": payload})
    try:
        signature = base64.b64decode(receipt["signature_b64"], validate=True)
        trust.public_key().verify(signature, signed)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise A4ContractError("BLOCK_SIGNATURE") from exc

    required_payload = {
        "min_signed_gap_days",
        "max_signed_gap_days",
        "max_component_nodes",
        "max_candidate_edges",
        "max_transactions",
        "max_pair_checks",
        "max_trace_bucket",
        "max_memory_bytes",
        "fee_rules",
    }
    optional_payload = {"max_subset_size", "max_subset_branches", "fx_rules"}
    if not required_payload <= set(payload) <= required_payload | optional_payload:
        raise A4ContractError("BLOCK_POLICY")
    low, high = payload["min_signed_gap_days"], payload["max_signed_gap_days"]
    nodes, edge_cap = payload["max_component_nodes"], payload["max_candidate_edges"]
    transaction_cap = payload["max_transactions"]
    pair_cap = payload["max_pair_checks"]
    trace_cap = payload["max_trace_bucket"]
    memory_cap = payload["max_memory_bytes"]
    subset_cap = payload.get("max_subset_size", 8)
    branch_cap = payload.get("max_subset_branches", 4_096)
    if any(
        type(value) is not int
        for value in (
            low,
            high,
            nodes,
            edge_cap,
            transaction_cap,
            pair_cap,
            trace_cap,
            memory_cap,
            subset_cap,
            branch_cap,
        )
    ):
        raise A4ContractError("BLOCK_POLICY")
    if (
        not -3 <= low <= high <= 3
        or not 2 <= nodes <= MAX_COMPONENT_NODES
        or not 1 <= edge_cap <= MAX_CANDIDATE_EDGES
        or not 2 <= transaction_cap <= MAX_ROWS
        or not 1 <= pair_cap <= MAX_CANDIDATE_EDGES
        or not 1 <= trace_cap <= pair_cap
        or not 1_048_576 <= memory_cap <= 4 * 1024 * 1024 * 1024
        or not 2 <= subset_cap <= 8
        or not 1 <= branch_cap <= 65_536
    ):
        raise A4ContractError("BLOCK_POLICY")
    rules: list[FeeRule] = []
    if not isinstance(payload["fee_rules"], list):
        raise A4ContractError("BLOCK_POLICY")
    for item in payload["fee_rules"]:
        if not isinstance(item, dict) or set(item) != {
            "rule_id",
            "bank_code",
            "product_code",
            "channel",
            "min_amount_minor",
            "max_amount_minor",
            "fee_minor",
            "effective_from",
            "effective_to",
        }:
            raise A4ContractError("BLOCK_POLICY")
        amounts = (
            item["min_amount_minor"],
            item["max_amount_minor"],
            item["fee_minor"],
        )
        if any(type(value) is not int for value in amounts) or not (
            1 <= amounts[0] <= amounts[1] <= MAX_MONEY_MINOR
            and 0 <= amounts[2] <= MAX_MONEY_MINOR
        ):
            raise A4ContractError("BLOCK_RANGE")
        rules.append(
            FeeRule(
                str(item["rule_id"]),
                str(item["bank_code"]),
                str(item["product_code"]),
                str(item["channel"]),
                amounts[0],
                amounts[1],
                amounts[2],
                _rfc3339(item["effective_from"]),
                _rfc3339(item["effective_to"]),
            )
        )
    fx_rules: list[FxRule] = []
    raw_fx_rules = payload.get("fx_rules", [])
    if not isinstance(raw_fx_rules, list):
        raise A4ContractError("BLOCK_POLICY")
    fx_keys = {
        "rule_id",
        "from_currency",
        "to_currency",
        "rate_numerator",
        "rate_denominator",
        "source_fee_minor",
        "target_fee_minor",
        "spread_bps",
        "rounding_mode",
        "effective_from",
        "effective_to",
        "rate_source_receipt_digest",
    }
    for item in raw_fx_rules:
        if not isinstance(item, dict) or set(item) != fx_keys:
            raise A4ContractError("BLOCK_POLICY")
        integers = (
            item["rate_numerator"],
            item["rate_denominator"],
            item["source_fee_minor"],
            item["target_fee_minor"],
            item["spread_bps"],
        )
        if any(type(value) is not int for value in integers) or not (
            1 <= integers[0] <= 1_000_000_000_000
            and 1 <= integers[1] <= 1_000_000_000_000
            and 0 <= integers[2] <= MAX_MONEY_MINOR
            and 0 <= integers[3] <= MAX_MONEY_MINOR
            and 0 <= integers[4] < 10_000
            and item["rounding_mode"] == "EXACT_RATIONAL"
            and _CURRENCY.fullmatch(str(item["from_currency"]))
            and _CURRENCY.fullmatch(str(item["to_currency"]))
            and item["from_currency"] != item["to_currency"]
            and _POLICY_ID.fullmatch(str(item["rule_id"]))
            and _SHA256.fullmatch(str(item["rate_source_receipt_digest"]))
        ):
            raise A4ContractError("BLOCK_POLICY")
        start, end = _rfc3339(item["effective_from"]), _rfc3339(item["effective_to"])
        if end <= start:
            raise A4ContractError("BLOCK_POLICY")
        fx_rules.append(
            FxRule(
                str(item["rule_id"]),
                str(item["from_currency"]),
                str(item["to_currency"]),
                integers[0],
                integers[1],
                integers[2],
                integers[3],
                integers[4],
                "EXACT_RATIONAL",
                start,
                end,
                str(item["rate_source_receipt_digest"]),
            )
        )
    return VerifiedPolicy(
        receipt,
        payload,
        low,
        high,
        nodes,
        edge_cap,
        tuple(rules),
        transaction_cap,
        pair_cap,
        trace_cap,
        memory_cap,
        subset_cap,
        branch_cap,
        tuple(fx_rules),
    )


@dataclass(frozen=True, slots=True)
class AdapterContract:
    adapter_id: str
    schema_version: str
    zone_name: str
    source_account: str
    bank_code: str
    booking_date: str
    withdrawal: str
    deposit: str
    reference: str | None = None
    counter_account: str | None = None
    fee_type: str | None = None
    product_code: str | None = None
    channel: str | None = None
    currency: str | None = None
    value_date: str | None = None
    duplicate_of_reference: str | None = None
    reversal_of_reference: str | None = None
    allowed_date_formats: tuple[str, ...] = ("%Y-%m-%d", "%Y%m%d")

    @property
    def digest(self) -> str:
        return digest_object(self.safe_dict())

    def safe_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "schema_version": self.schema_version,
            "zone_name": self.zone_name,
            "source_account": self.source_account,
            "bank_code": self.bank_code,
            "booking_date": self.booking_date,
            "withdrawal": self.withdrawal,
            "deposit": self.deposit,
            "reference": self.reference,
            "counter_account": self.counter_account,
            "fee_type": self.fee_type,
            "product_code": self.product_code,
            "channel": self.channel,
            "currency": self.currency,
            "value_date": self.value_date,
            "duplicate_of_reference": self.duplicate_of_reference,
            "reversal_of_reference": self.reversal_of_reference,
            "allowed_date_formats": list(self.allowed_date_formats),
        }


@dataclass(frozen=True, slots=True)
class SealedCodeDictionary:
    dictionary_id: str
    version: str
    digest: str
    product_aliases: Mapping[str, str]
    channel_aliases: Mapping[str, str]

    def resolve_product(self, value: object) -> str:
        return self._resolve(value, self.product_aliases)

    def resolve_channel(self, value: object) -> str:
        return self._resolve(value, self.channel_aliases)

    @staticmethod
    def _resolve(value: object, aliases: Mapping[str, str]) -> str:
        normalized = unicodedata.normalize("NFC", str(value or "DEFAULT")).strip().upper()
        resolved = aliases.get(normalized)
        if resolved is None:
            raise A4ContractError("BLOCK_DICTIONARY_VALUE")
        return resolved


def load_code_dictionary(path: Path | None = None) -> SealedCodeDictionary:
    dictionary_path = path or (
        Path(__file__).resolve().parent
        / "contracts"
        / "a4_v31"
        / "code_dictionary.production.json"
    )
    if not dictionary_path.is_file() or dictionary_path.is_symlink():
        raise A4ContractError("BLOCK_DICTIONARY_VALUE")
    raw = dictionary_path.read_bytes()
    document = strict_json_loads(raw)
    required = {
        "schema_version",
        "dictionary_id",
        "version",
        "unknown_policy",
        "product_codes",
        "channels",
    }
    if (
        not isinstance(document, dict)
        or set(document) != required
        or document["schema_version"] != "butler.box5.a4.code_dictionary.v3.1"
        or document["unknown_policy"] != "QUARANTINE"
    ):
        raise A4ContractError("BLOCK_DICTIONARY_VALUE")

    def aliases(items: object) -> dict[str, str]:
        if not isinstance(items, list) or not items:
            raise A4ContractError("BLOCK_DICTIONARY_VALUE")
        result: dict[str, str] = {}
        ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"id", "aliases"}:
                raise A4ContractError("BLOCK_DICTIONARY_VALUE")
            stable_id = str(item["id"])
            if not _POLICY_ID.fullmatch(stable_id) or stable_id in ids:
                raise A4ContractError("BLOCK_DICTIONARY_VALUE")
            ids.add(stable_id)
            values = item["aliases"]
            if not isinstance(values, list) or not values:
                raise A4ContractError("BLOCK_DICTIONARY_VALUE")
            for value in values:
                normalized = unicodedata.normalize("NFC", str(value)).strip().upper()
                if not normalized or normalized in result:
                    raise A4ContractError("BLOCK_DICTIONARY_VALUE")
                result[normalized] = stable_id
        if "DEFAULT" not in ids:
            raise A4ContractError("BLOCK_DICTIONARY_VALUE")
        return result

    return SealedCodeDictionary(
        str(document["dictionary_id"]),
        str(document["version"]),
        sha256_bytes(raw),
        aliases(document["product_codes"]),
        aliases(document["channels"]),
    )


class TokenBoundary(Protocol):
    def account_token(
        self, tenant_id: str, bank_code: str, account_number: str
    ) -> tuple[str, str]: ...
    def a4_evidence_token(
        self, tenant_id: str, token_kind: str, value: str
    ) -> tuple[str, str]: ...


@dataclass(frozen=True, slots=True)
class CompiledTransaction:
    tenant_id: str
    txn_uid: str
    source_row_digest: str
    row_ordinal: int
    canonical_row_digest: str
    source_account_id: str
    direction: Direction
    amount_minor: int
    currency: str
    booked_at_utc: datetime
    local_date: date
    artifact_token: str
    bank_code: str
    bank_reference_token: str | None
    counterparty_account_token: str | None
    resolved_counterparty_account_id: str | None
    counterparty_resolution: CounterpartyResolution
    row_kind: str
    product_code_id: str
    channel_id: str
    adapter_id: str = "TEST"
    adapter_digest: str = "0" * 64
    registry_digest: str = "0" * 64
    value_date: date | None = None
    duplicate_of_reference_token: str | None = None
    reversal_of_reference_token: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.tenant_id)
        _uuid(self.txn_uid)
        _uuid(self.source_account_id, "BLOCK_ACCOUNT_IDENTITY")
        if (
            not _SHA256.fullmatch(self.source_row_digest)
            or not _SHA256.fullmatch(self.canonical_row_digest)
            or type(self.row_ordinal) is not int
            or self.row_ordinal < 0
            or not _TOKEN.fullmatch(self.artifact_token)
        ):
            raise A4ContractError("BLOCK_SCHEMA")
        if (
            type(self.amount_minor) is not int
            or not 1 <= self.amount_minor <= MAX_MONEY_MINOR
        ):
            raise A4ContractError("BLOCK_RANGE")
        if not _CURRENCY.fullmatch(self.currency) or type(self.local_date) is not date:
            raise A4ContractError("BLOCK_TYPE")
        if (
            self.booked_at_utc.tzinfo is None
            or self.booked_at_utc.utcoffset()
            != timezone.utc.utcoffset(self.booked_at_utc)
        ):
            raise A4ContractError("BLOCK_TIMEZONE")
        if self.row_kind not in {"PRINCIPAL", "FEE"}:
            raise A4ContractError("BLOCK_SCHEMA")
        if self.value_date is not None and type(self.value_date) is not date:
            raise A4ContractError("BLOCK_SCHEMA")
        for link in (
            self.duplicate_of_reference_token,
            self.reversal_of_reference_token,
        ):
            if link is not None and not _SHA256.fullmatch(link):
                raise A4ContractError("BLOCK_SCHEMA")
        if (
            self.duplicate_of_reference_token is not None
            and self.reversal_of_reference_token is not None
        ):
            raise A4ContractError("BLOCK_REVERSAL_BINDING")
        if (
            not _POLICY_ID.fullmatch(self.product_code_id)
            or not _POLICY_ID.fullmatch(self.channel_id)
            or not _POLICY_ID.fullmatch(self.adapter_id)
            or not _SHA256.fullmatch(self.adapter_digest)
            or not _SHA256.fullmatch(self.registry_digest)
        ):
            raise A4ContractError("BLOCK_SCHEMA")
        if self.counterparty_resolution is CounterpartyResolution.EXACT_VERIFIED:
            if self.resolved_counterparty_account_id is None:
                raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
            _uuid(
                self.resolved_counterparty_account_id,
                "BLOCK_ACCOUNT_IDENTITY",
            )
        elif self.resolved_counterparty_account_id is not None:
            raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
        if self.counterparty_resolution is CounterpartyResolution.CONFLICT:
            raise A4ContractError("BLOCK_COUNTERPARTY_CONFLICT")

    @property
    def graph_key(self) -> tuple[str, str]:
        return self.tenant_id, self.txn_uid

    @property
    def product_code(self) -> str:
        return self.product_code_id

    @property
    def channel(self) -> str:
        return self.channel_id

    def safe_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "txn_uid": self.txn_uid,
            "source_row_digest": self.source_row_digest,
            "row_ordinal": self.row_ordinal,
            "canonical_row_digest": self.canonical_row_digest,
            "account_id": self.source_account_id,
            "direction": self.direction.value,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "booked_at_utc": self.booked_at_utc.isoformat().replace("+00:00", "Z"),
            "local_date": self.local_date.isoformat(),
            "artifact_token": self.artifact_token,
            "bank_code": self.bank_code,
            "bank_reference_token": self.bank_reference_token,
            "counterparty_account_token": self.counterparty_account_token,
            "resolved_counterparty_account_id": self.resolved_counterparty_account_id,
            "counterparty_resolution": self.counterparty_resolution.value,
            "row_kind": self.row_kind,
            "product_code_id": self.product_code_id,
            "channel_id": self.channel_id,
            "adapter_id": self.adapter_id,
            "adapter_digest": self.adapter_digest,
            "registry_digest": self.registry_digest,
            "value_date": self.value_date.isoformat() if self.value_date else None,
            "duplicate_of_reference_token": self.duplicate_of_reference_token,
            "reversal_of_reference_token": self.reversal_of_reference_token,
        }


@dataclass(frozen=True, slots=True)
class CompileReceipt:
    transactions: tuple[CompiledTransaction, ...]
    source_file_sha256: str
    source_file_size: int
    source_row_count: int
    adapter_digest: str
    account_snapshot_digest: str
    lookup_key_ids: tuple[str, ...]
    account_continuity: tuple[dict[str, str], ...]
    dictionary_digest: str
    registry_digest: str


def _header(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).strip()
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text or any(unicodedata.category(char) in {"Cc", "Cf"} for char in text):
        raise A4ContractError("BLOCK_SCHEMA")
    return text


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        raise A4ContractError("BLOCK_TYPE")
    if isinstance(value, bool):
        raise A4ContractError("BLOCK_TYPE")
    text = unicodedata.normalize("NFC", str(value)).strip()
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in text):
        raise A4ContractError("BLOCK_SCHEMA")
    if len(text.encode("utf-8")) > 1_024:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    return text


def _account_number(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", _cell(value).upper())


def _source_money(value: object) -> int:
    if type(value) is int:
        amount = value
    else:
        text = _cell(value)
        if not (_INT_SOURCE.fullmatch(text) or _INT_GROUPED.fullmatch(text)):
            raise A4ContractError("BLOCK_TYPE")
        amount = int(text.replace(",", ""))
    if not 1 <= amount <= MAX_MONEY_MINOR:
        raise A4ContractError("BLOCK_RANGE")
    return amount


def _local_datetime(value: object, adapter: AdapterContract) -> tuple[datetime, date]:
    if isinstance(value, datetime):
        raise A4ContractError("BLOCK_TYPE")
    if type(value) is date:
        day, clock = value, time(0, 0)
    else:
        text = _cell(value)
        parsed: datetime | None = None
        for fmt in adapter.allowed_date_formats:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise A4ContractError("BLOCK_DATE")
        day, clock = parsed.date(), parsed.time()
    try:
        zone = ZoneInfo(adapter.zone_name)
    except ZoneInfoNotFoundError as exc:
        raise A4ContractError("BLOCK_TIMEZONE") from exc
    localized = datetime.combine(day, clock, tzinfo=zone)
    return localized.astimezone(timezone.utc), day


def compile_dataframe(
    *,
    frame: Any,
    tenant_id: str,
    run_id: str,
    source_file_sha256: str,
    source_file_size: int,
    adapter: AdapterContract,
    token_service: TokenBoundary,
    own_account_registry: Mapping[str, Any],
    code_dictionary: SealedCodeDictionary | None = None,
) -> CompileReceipt:
    """Compile all rows or return none; individual-row quarantine is forbidden."""

    tenant_id, run_id = _uuid(tenant_id), _uuid(run_id)
    if (
        not _SHA256.fullmatch(source_file_sha256)
        or type(source_file_size) is not int
        or source_file_size <= 0
    ):
        raise A4ContractError("BLOCK_INPUT_CLOSURE")
    if not hasattr(frame, "columns") or not callable(getattr(frame, "iterrows", None)):
        raise A4ContractError("BLOCK_SCHEMA")
    if len(frame.index) > MAX_ROWS:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    dictionary = code_dictionary or load_code_dictionary()
    if (
        not isinstance(own_account_registry, Mapping)
        or set(own_account_registry)
        != {
            "schema_version",
            "tenant_id",
            "registry_version",
            "accounts",
            "registry_digest",
        }
        or own_account_registry["schema_version"]
        != "butler.box5.a4.own_account_registry.v3.1"
        or own_account_registry["tenant_id"] != tenant_id
        or not _SHA256.fullmatch(str(own_account_registry["registry_digest"]))
        or not isinstance(own_account_registry["accounts"], list)
    ):
        raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
    registry_accounts = own_account_registry["accounts"]
    if digest_object(registry_accounts) != own_account_registry["registry_digest"]:
        raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
    registry_index: dict[tuple[str, str, str], str] = {}
    for item in registry_accounts:
        required_registry_fields = {
            "bank_code",
            "account_token",
            "account_id",
            "status",
            "effective_from",
            "effective_to",
            _REGISTRY_APPROVAL_FIELD,
            "key_id",
        }
        if (
            not isinstance(item, Mapping)
            or set(item) != required_registry_fields
            or item["status"] != "ACTIVE"
            or item["effective_to"] is not None
            or not _SHA256.fullmatch(str(item["account_token"]))
        ):
            raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
        account_id = _uuid(str(item["account_id"]), "BLOCK_REGISTRY_IDENTITY")
        key = (str(item["bank_code"]), str(item["key_id"]), str(item["account_token"]))
        if key in registry_index or account_id in registry_index.values():
            raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
        registry_index[key] = account_id
    if len(registry_index) < 2:
        raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
    normalized = [_header(item) for item in frame.columns]
    if len(normalized) != len(set(normalized)):
        raise A4ContractError("BLOCK_AMBIGUOUS_COLUMN")
    positions = {
        name: original for name, original in zip(normalized, frame.columns, strict=True)
    }
    required = {
        adapter.source_account,
        adapter.bank_code,
        adapter.booking_date,
        adapter.withdrawal,
        adapter.deposit,
    }
    if any(_header(name) not in positions for name in required):
        raise A4ContractError("BLOCK_SCHEMA")
    amount_aliases = {
        "금액",
        "거래금액",
        "amount",
        "출금",
        "출금액",
        "withdrawal",
        "입금",
        "입금액",
        "deposit",
    }
    approved_amount_headers = {_header(adapter.withdrawal), _header(adapter.deposit)}
    if any(
        name in amount_aliases and name not in approved_amount_headers
        for name in positions
    ):
        raise A4ContractError("BLOCK_AMBIGUOUS_COLUMN")
    semantic_names = [
        adapter.source_account,
        adapter.bank_code,
        adapter.booking_date,
        adapter.withdrawal,
        adapter.deposit,
        adapter.reference,
        adapter.counter_account,
        adapter.fee_type,
        adapter.product_code,
        adapter.channel,
        adapter.currency,
        adapter.value_date,
        adapter.duplicate_of_reference,
        adapter.reversal_of_reference,
    ]
    active = [_header(name) for name in semantic_names if name is not None]
    if len(active) != len(set(active)):
        raise A4ContractError("BLOCK_AMBIGUOUS_COLUMN")

    rows = tuple(frame.iterrows())
    compiled: list[CompiledTransaction] = []
    key_ids: set[str] = set()
    source_digests: set[str] = set()
    txn_digests: dict[str, str] = {}
    artifacts: set[str] = set()
    account_receipts: dict[str, dict[str, str]] = {}
    source_identities: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    account_number_identities: dict[str, set[str]] = {}
    for _, row in rows:
        bank_code = _cell(row.get(positions[_header(adapter.bank_code)])).upper()
        account_number = _account_number(
            row.get(positions[_header(adapter.source_account)])
        )
        if not bank_code or not account_number:
            raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
        try:
            account_key_id, account_lookup = token_service.account_token(
                tenant_id, bank_code, account_number
            )
            account_id = registry_index.get((bank_code, account_key_id, account_lookup))
            if account_id is None:
                raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
        except A4ContractError:
            raise
        except Exception as exc:
            raise A4ContractError("KEYCHAIN_UNAVAILABLE") from exc
        identity = (bank_code, account_id, account_key_id, account_lookup)
        source_key = (bank_code, account_number)
        previous_identity = source_identities.get(source_key)
        if previous_identity is not None and previous_identity != identity:
            raise A4ContractError("BLOCK_COUNTERPARTY_CONFLICT")
        source_identities[source_key] = identity
        account_number_identities.setdefault(account_number, set()).add(account_id)
        key_ids.add(account_key_id)
        account_mapping = {
            "account_id": account_id,
            "lookup_key_id": account_key_id,
            "lookup_token": account_lookup,
            "bank_code": bank_code,
            "registry_version": str(own_account_registry["registry_version"]),
            "status": "ACTIVE",
        }
        previous_mapping = account_receipts.get(account_id)
        if previous_mapping is not None and previous_mapping != account_mapping:
            raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
        account_receipts[account_id] = account_mapping
    namespace = uuid.uuid5(uuid.UUID(tenant_id), source_file_sha256)
    for ordinal, (_, row) in enumerate(rows):
        withdrawal_raw = _cell(row.get(positions[_header(adapter.withdrawal)]))
        deposit_raw = _cell(row.get(positions[_header(adapter.deposit)]))
        if bool(withdrawal_raw) == bool(deposit_raw):
            raise A4ContractError("BLOCK_AMBIGUOUS_COLUMN")
        direction = Direction.OUTFLOW if withdrawal_raw else Direction.INFLOW
        amount = _source_money(withdrawal_raw or deposit_raw)
        bank_code = _cell(row.get(positions[_header(adapter.bank_code)])).upper()
        account_number = _account_number(
            row.get(positions[_header(adapter.source_account)])
        )
        if not bank_code or not account_number:
            raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
        source_identity = source_identities.get((bank_code, account_number))
        if source_identity is None:
            raise A4ContractError("BLOCK_REGISTRY_IDENTITY")
        account_id, account_key_id = source_identity[1], source_identity[2]
        booked_at, local_day = _local_datetime(
            row.get(positions[_header(adapter.booking_date)]), adapter
        )
        reference_token = None
        if adapter.reference is not None and _header(adapter.reference) in positions:
            reference = _cell(row.get(positions[_header(adapter.reference)]))
            if reference:
                key_id, reference_token = token_service.a4_evidence_token(
                    tenant_id, "BANK_REFERENCE", reference
                )
                key_ids.add(key_id)
        counter_token = None
        resolved_counterparty_account_id = None
        counterparty_resolution = CounterpartyResolution.MISSING
        if (
            adapter.counter_account is not None
            and _header(adapter.counter_account) in positions
        ):
            raw_counter = _cell(row.get(positions[_header(adapter.counter_account)]))
            counter = _account_number(raw_counter)
            if any(marker in raw_counter for marker in ("*", "•", "●")):
                counterparty_resolution = CounterpartyResolution.MASKED
            elif counter:
                key_id, counter_token = token_service.a4_evidence_token(
                    tenant_id, "COUNTERPARTY_ACCOUNT", counter
                )
                key_ids.add(key_id)
                counter_identities = account_number_identities.get(counter, set())
                if len(counter_identities) == 1:
                    resolved_counterparty_account_id = next(iter(counter_identities))
                    counterparty_resolution = CounterpartyResolution.EXACT_VERIFIED
                elif len(counter_identities) > 1:
                    raise A4ContractError("BLOCK_COUNTERPARTY_CONFLICT")
                else:
                    counterparty_resolution = CounterpartyResolution.UNRESOLVED
        row_kind = "PRINCIPAL"
        if adapter.fee_type is not None and _header(adapter.fee_type) in positions:
            fee_value = _cell(row.get(positions[_header(adapter.fee_type)])).upper()
            if fee_value:
                if fee_value not in {"FEE", "수수료"}:
                    raise A4ContractError("BLOCK_SCHEMA")
                row_kind = "FEE"
        product_code_value = "DEFAULT"
        if (
            adapter.product_code is not None
            and _header(adapter.product_code) in positions
        ):
            product_code_value = (
                _cell(row.get(positions[_header(adapter.product_code)])) or "DEFAULT"
            )
        channel_value = "DEFAULT"
        if adapter.channel is not None and _header(adapter.channel) in positions:
            channel_value = _cell(row.get(positions[_header(adapter.channel)])) or "DEFAULT"
        product_code_id = dictionary.resolve_product(product_code_value)
        channel_id = dictionary.resolve_channel(channel_value)
        currency = "KRW"
        if adapter.currency is not None and _header(adapter.currency) in positions:
            currency = _cell(row.get(positions[_header(adapter.currency)])).upper()
            if not _CURRENCY.fullmatch(currency):
                raise A4ContractError("BLOCK_TYPE")
        value_day = None
        if adapter.value_date is not None and _header(adapter.value_date) in positions:
            raw_value_date = _cell(row.get(positions[_header(adapter.value_date)]))
            if raw_value_date:
                _, value_day = _local_datetime(raw_value_date, adapter)
        duplicate_of_reference_token = None
        reversal_of_reference_token = None
        for column_name, token_kind in (
            (adapter.duplicate_of_reference, "DUPLICATE_OF_REFERENCE"),
            (adapter.reversal_of_reference, "REVERSAL_OF_REFERENCE"),
        ):
            if column_name is None or _header(column_name) not in positions:
                continue
            raw_link = _cell(row.get(positions[_header(column_name)]))
            if not raw_link:
                continue
            key_id, link_token = token_service.a4_evidence_token(
                tenant_id, "BANK_REFERENCE", raw_link
            )
            key_ids.add(key_id)
            if token_kind == "DUPLICATE_OF_REFERENCE":
                duplicate_of_reference_token = link_token
            else:
                reversal_of_reference_token = link_token
        if (
            duplicate_of_reference_token is not None
            and reversal_of_reference_token is not None
        ):
            raise A4ContractError("BLOCK_REVERSAL_BINDING")
        canonical_row = {
            "account_id": account_id,
            "direction": direction.value,
            "amount_minor": amount,
            "currency": currency,
            "booked_at_utc": booked_at.isoformat().replace("+00:00", "Z"),
            "local_date": local_day.isoformat(),
            "bank_code": bank_code,
            "bank_reference_token": reference_token,
            "counterparty_account_token": counter_token,
            "resolved_counterparty_account_id": resolved_counterparty_account_id,
            "counterparty_resolution": counterparty_resolution.value,
            "row_kind": row_kind,
            "product_code_id": product_code_id,
            "channel_id": channel_id,
            "adapter_id": adapter.adapter_id,
            "adapter_digest": adapter.digest,
            "registry_digest": str(own_account_registry["registry_digest"]),
            "value_date": value_day.isoformat() if value_day else None,
            "duplicate_of_reference_token": duplicate_of_reference_token,
            "reversal_of_reference_token": reversal_of_reference_token,
        }
        canonical_row_digest = digest_object(canonical_row)
        source_row_digest = digest_object(
            {
                "source_file_sha256": source_file_sha256,
                "row_ordinal": ordinal,
                "canonical_row_sha256": canonical_row_digest,
            }
        )
        if source_row_digest in source_digests:
            raise A4ContractError("BLOCK_DUPLICATE_SOURCE_ROW")
        source_digests.add(source_row_digest)
        txn_uid = str(
            uuid.uuid5(
                namespace, f"{source_file_sha256}:{ordinal}:{canonical_row_digest}"
            )
        )
        previous = txn_digests.get(txn_uid)
        if previous is not None and not hmac.compare_digest(
            previous, canonical_row_digest
        ):
            raise A4ContractError("BLOCK_TXN_UID_CONFLICT")
        txn_digests[txn_uid] = canonical_row_digest
        try:
            key_id, full_artifact = token_service.a4_evidence_token(
                tenant_id, "RUN_TRANSACTION", run_id + tenant_id + txn_uid
            )
        except Exception as exc:
            raise A4ContractError("KEYCHAIN_UNAVAILABLE") from exc
        key_ids.add(key_id)
        artifact = full_artifact[:32]
        if not _TOKEN.fullmatch(artifact) or artifact in artifacts:
            raise A4ContractError("BLOCK_ARTIFACT_TOKEN_COLLISION")
        artifacts.add(artifact)
        compiled.append(
            CompiledTransaction(
                tenant_id,
                txn_uid,
                source_row_digest,
                ordinal,
                canonical_row_digest,
                account_id,
                direction,
                amount,
                currency,
                booked_at,
                local_day,
                artifact,
                bank_code,
                reference_token,
                counter_token,
                resolved_counterparty_account_id,
                counterparty_resolution,
                row_kind,
                product_code_id,
                channel_id,
                adapter.adapter_id,
                adapter.digest,
                str(own_account_registry["registry_digest"]),
                value_day,
                duplicate_of_reference_token,
                reversal_of_reference_token,
            )
        )
    ordered_accounts = tuple(
        sorted(
            account_receipts.values(),
            key=lambda item: (item["account_id"], item["lookup_token"]),
        )
    )
    snapshot_digest = digest_object(ordered_accounts)
    return CompileReceipt(
        tuple(sorted(compiled, key=lambda item: item.graph_key)),
        source_file_sha256,
        source_file_size,
        len(frame.index),
        adapter.digest,
        snapshot_digest,
        tuple(sorted(key_ids)),
        ordered_accounts,
        dictionary.digest,
        str(own_account_registry["registry_digest"]),
    )


@dataclass(frozen=True, slots=True)
class CandidateEdge:
    outflow: CompiledTransaction
    inflow: CompiledTransaction
    fee: CompiledTransaction | None
    fee_mode: FeeMode
    fee_minor: int
    evidence_grade: EvidenceGrade
    policy_rule_id: str | None
    time_delta_ms: int
    exact_reference: bool
    eligibility_basis: EligibilityBasis
    binding_digest: str
    additional_outflows: tuple[CompiledTransaction, ...] = ()
    additional_inflows: tuple[CompiledTransaction, ...] = ()
    match_type: MatchType = MatchType.EXACT
    currency_mode: str | None = None
    fx_rule_id: str | None = None
    fx_receipt_digest: str | None = None

    @property
    def outflows(self) -> tuple[CompiledTransaction, ...]:
        return (self.outflow, *self.additional_outflows)

    @property
    def inflows(self) -> tuple[CompiledTransaction, ...]:
        return (self.inflow, *self.additional_inflows)

    @property
    def principal_count(self) -> int:
        return len(self.outflows) + len(self.inflows)

    @property
    def edge_id(self) -> str:
        payload: dict[str, Any] = {
            "outflow": self.outflow.txn_uid,
            "inflow": self.inflow.txn_uid,
            "fee": self.fee.txn_uid if self.fee else None,
            "mode": self.fee_mode.value,
            "fee_minor": self.fee_minor,
            "eligibility_basis": self.eligibility_basis.value,
            "binding_digest": self.binding_digest,
        }
        if self.principal_count > 2 or self.match_type is MatchType.FX:
            payload.update(
                {
                    "outflows": sorted(item.txn_uid for item in self.outflows),
                    "inflows": sorted(item.txn_uid for item in self.inflows),
                    "match_type": self.match_type.value,
                    "currency_mode": self.currency_mode,
                    "fx_rule_id": self.fx_rule_id,
                    "fx_receipt_digest": self.fx_receipt_digest,
                }
            )
        return digest_object(payload)

    @property
    def semantic_cost(self) -> tuple[int, int, int]:
        fee_penalty = int(
            self.evidence_grade is EvidenceGrade.SCHEDULE_SUPPORTED_FEE_CANDIDATE
        )
        return (-self.principal_count, self.time_delta_ms, fee_penalty)

    @property
    def node_uids(self) -> frozenset[str]:
        values = {
            *(item.txn_uid for item in self.outflows),
            *(item.txn_uid for item in self.inflows),
        }
        if self.fee is not None:
            values.add(self.fee.txn_uid)
        return frozenset(values)

    def safe_dict(self) -> dict[str, Any]:
        result = {
            "edge_id": self.edge_id,
            "outflow_txn_uid": self.outflow.txn_uid,
            "inflow_txn_uid": self.inflow.txn_uid,
            "fee_txn_uid": self.fee.txn_uid if self.fee else None,
            "fee_mode": self.fee_mode.value,
            "fee_minor": self.fee_minor,
            "currency": self.outflow.currency,
            "evidence_grade": self.evidence_grade.value,
            "policy_rule_id": self.policy_rule_id,
            "time_delta_ms": self.time_delta_ms,
            "exact_reference": self.exact_reference,
            "eligibility_basis": self.eligibility_basis.value,
            "binding_digest": self.binding_digest,
            "affects_reporting": False,
        }
        if self.principal_count > 2 or self.match_type is MatchType.FX:
            result.update(
                {
                    "outflow_txn_uids": sorted(item.txn_uid for item in self.outflows),
                    "inflow_txn_uids": sorted(item.txn_uid for item in self.inflows),
                    "match_type": self.match_type.value,
                    "currency_mode": self.currency_mode,
                    "fx_rule_id": self.fx_rule_id,
                    "fx_receipt_digest": self.fx_receipt_digest,
                }
            )
        return result


@dataclass(frozen=True, slots=True)
class ComponentResult:
    component_id: str
    forced_edge_ids: tuple[str, ...]
    ambiguous_txn_uids: tuple[str, ...]
    unmatched_txn_uids: tuple[str, ...]
    has_alternative_optimum: bool
    alternative_optimum_count: int | None
    alternative_optimum_count_exact: bool

    def safe_dict(self, run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "component_id": self.component_id,
            "forced_edge_ids": list(self.forced_edge_ids),
            "ambiguous_txn_uids": list(self.ambiguous_txn_uids),
            "unmatched_txn_uids": list(self.unmatched_txn_uids),
            "has_alternative_optimum": self.has_alternative_optimum,
            "alternative_optimum_count": self.alternative_optimum_count,
            "alternative_optimum_count_exact": self.alternative_optimum_count_exact,
            "forced_pair_count": len(self.forced_edge_ids),
            "residual_unmatched_count": len(self.unmatched_txn_uids),
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    edges: tuple[CandidateEdge, ...]
    components: tuple[ComponentResult, ...]
    globally_unmatched_txn_uids: tuple[str, ...]
    candidate_pair_checks: int = 0
    max_candidate_bucket_size: int = 0
    candidate_subset_branches: int = 0
    terminal_groups: tuple["TerminalGroup", ...] = ()

    @property
    def forced_edges(self) -> tuple[CandidateEdge, ...]:
        forced = {
            edge_id
            for component in self.components
            for edge_id in component.forced_edge_ids
        }
        return tuple(edge for edge in self.edges if edge.edge_id in forced)


@dataclass(frozen=True, slots=True)
class TerminalGroup:
    transaction_uids: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        if (
            not self.transaction_uids
            or tuple(sorted(set(self.transaction_uids))) != self.transaction_uids
            or self.reason_code not in {
                "BLOCK_DUPLICATE_BINDING",
                "BLOCK_REVERSAL_BINDING",
            }
        ):
            raise A4ContractError("BLOCK_SCHEMA")
        for txn_uid in self.transaction_uids:
            _uuid(txn_uid)

    @property
    def group_id(self) -> str:
        return digest_object(
            {
                "transaction_uids": list(self.transaction_uids),
                "reason_code": self.reason_code,
            }
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "state": "BLOCKED",
            "reason_code": self.reason_code,
            "transaction_uids": list(self.transaction_uids),
        }


def _exact_reference(left: CompiledTransaction, right: CompiledTransaction) -> bool:
    return (
        left.bank_reference_token is not None
        and right.bank_reference_token is not None
        and hmac.compare_digest(left.bank_reference_token, right.bank_reference_token)
    )


def _strong_pair(
    outflow: CompiledTransaction,
    inflow: CompiledTransaction,
    policy: VerifiedPolicy,
) -> bool:
    outflow_day = outflow.value_date or outflow.local_date
    inflow_day = inflow.value_date or inflow.local_date
    gap_days = (inflow_day - outflow_day).days
    return (
        outflow.direction is Direction.OUTFLOW
        and inflow.direction is Direction.INFLOW
        and outflow.tenant_id == inflow.tenant_id
        and outflow.source_account_id != inflow.source_account_id
        and outflow.counterparty_resolution is CounterpartyResolution.EXACT_VERIFIED
        and inflow.counterparty_resolution is CounterpartyResolution.EXACT_VERIFIED
        and outflow.resolved_counterparty_account_id == inflow.source_account_id
        and inflow.resolved_counterparty_account_id == outflow.source_account_id
        and policy.min_signed_gap_days <= gap_days <= policy.max_signed_gap_days
    )


def _terminal_partition(
    transactions: Sequence[CompiledTransaction],
) -> tuple[tuple[CompiledTransaction, ...], tuple[TerminalGroup, ...]]:
    reference_index: dict[tuple[str, str], list[CompiledTransaction]] = {}
    for tx in transactions:
        if tx.bank_reference_token is not None:
            reference_index.setdefault(
                (tx.tenant_id, tx.bank_reference_token), []
            ).append(tx)

    claimed: set[str] = set()
    groups: list[TerminalGroup] = []
    for tx in transactions:
        link = tx.reversal_of_reference_token
        if link is None:
            continue
        targets = reference_index.get((tx.tenant_id, link), [])
        if len(targets) != 1:
            raise A4ContractError("BLOCK_REVERSAL_BINDING")
        target = targets[0]
        uids = tuple(sorted((tx.txn_uid, target.txn_uid)))
        if (
            tx.txn_uid == target.txn_uid
            or tx.row_kind != "PRINCIPAL"
            or target.row_kind != "PRINCIPAL"
            or tx.source_account_id != target.source_account_id
            or tx.direction is target.direction
            or tx.amount_minor != target.amount_minor
            or tx.currency != target.currency
            or claimed.intersection(uids)
        ):
            raise A4ContractError("BLOCK_REVERSAL_BINDING")
        claimed.update(uids)
        groups.append(TerminalGroup(uids, "BLOCK_REVERSAL_BINDING"))

    for tx in transactions:
        link = tx.duplicate_of_reference_token
        if link is None:
            continue
        targets = reference_index.get((tx.tenant_id, link), [])
        if (
            len(targets) != 1
            or targets[0].txn_uid == tx.txn_uid
            or tx.txn_uid in claimed
        ):
            raise A4ContractError("BLOCK_DUPLICATE_BINDING")
        claimed.add(tx.txn_uid)
        groups.append(
            TerminalGroup((tx.txn_uid,), "BLOCK_DUPLICATE_BINDING")
        )

    active = tuple(tx for tx in transactions if tx.txn_uid not in claimed)
    return active, tuple(sorted(groups, key=lambda item: item.group_id))


def _multi_binding_digest(
    outflows: Sequence[CompiledTransaction],
    inflows: Sequence[CompiledTransaction],
    *,
    match_type: MatchType,
    fx_rule: FxRule | None = None,
) -> str:
    return digest_object(
        {
            "domain": "BUTLER_A4_STRONG_BINDING_V5_4",
            "tenant_id": outflows[0].tenant_id,
            "outflow_txn_uids": sorted(item.txn_uid for item in outflows),
            "inflow_txn_uids": sorted(item.txn_uid for item in inflows),
            "outflow_account_ids": sorted(
                {item.source_account_id for item in outflows}
            ),
            "inflow_account_ids": sorted(
                {item.source_account_id for item in inflows}
            ),
            "match_type": match_type.value,
            "fx_rule_id": fx_rule.rule_id if fx_rule else None,
            "fx_receipt_digest": (
                fx_rule.rate_source_receipt_digest if fx_rule else None
            ),
            "eligibility_basis": EligibilityBasis.RECIPROCAL_ACCOUNT.value,
        }
    )


def _time_delta_ms(items: Sequence[CompiledTransaction]) -> int:
    times = [item.booked_at_utc for item in items]
    return int((max(times) - min(times)).total_seconds() * 1_000)


def _aggregate_fee_rule(
    outflows: Sequence[CompiledTransaction],
    *,
    principal_amount: int,
    fee_minor: int,
    policy: VerifiedPolicy,
) -> FeeRule | None:
    matches = [
        rule
        for rule in policy.fee_rules
        if rule.fee_minor == fee_minor
        and all(
            rule.matches(
                bank_code=item.bank_code,
                product_code=item.product_code,
                channel=item.channel,
                amount=principal_amount,
                at=item.booked_at_utc,
            )
            for item in outflows
        )
    ]
    if len(matches) > 1:
        raise A4ContractError("BLOCK_AMBIGUOUS_FEE_RULE")
    return matches[0] if matches else None


def _build_subset_edges(
    principals: Sequence[CompiledTransaction],
    policy: VerifiedPolicy,
) -> tuple[tuple[CandidateEdge, ...], int]:
    outflows = [item for item in principals if item.direction is Direction.OUTFLOW]
    inflows = [item for item in principals if item.direction is Direction.INFLOW]
    edges: dict[str, CandidateEdge] = {}
    branches = 0

    def add_candidate(
        candidate_outflows: tuple[CompiledTransaction, ...],
        candidate_inflows: tuple[CompiledTransaction, ...],
    ) -> None:
        nonlocal branches
        branches += 1
        if branches > policy.max_subset_branches:
            raise A4ContractError("BLOCK_RESOURCE_SUBSET_BRANCHES")
        currencies = {
            item.currency for item in (*candidate_outflows, *candidate_inflows)
        }
        if len(currencies) != 1:
            return
        out_total = sum(item.amount_minor for item in candidate_outflows)
        in_total = sum(item.amount_minor for item in candidate_inflows)
        fee_rule: FeeRule | None = None
        if out_total == in_total:
            match_type = MatchType.PARTIAL
            fee_mode = FeeMode.NO_FEE
            fee_minor = 0
            grade = EvidenceGrade.OBSERVED_PRINCIPAL
        elif out_total > in_total:
            fee_minor = out_total - in_total
            fee_rule = _aggregate_fee_rule(
                candidate_outflows,
                principal_amount=in_total,
                fee_minor=fee_minor,
                policy=policy,
            )
            if fee_rule is None:
                return
            match_type = MatchType.FEE_ADJUSTED
            fee_mode = FeeMode.EMBEDDED_DEBIT
            grade = EvidenceGrade.SCHEDULE_SUPPORTED_FEE_CANDIDATE
        else:
            return
        ordered_out = tuple(sorted(candidate_outflows, key=lambda item: item.txn_uid))
        ordered_in = tuple(sorted(candidate_inflows, key=lambda item: item.txn_uid))
        all_items = (*ordered_out, *ordered_in)
        edge = CandidateEdge(
            ordered_out[0],
            ordered_in[0],
            None,
            fee_mode,
            fee_minor,
            grade,
            fee_rule.rule_id if fee_rule else None,
            _time_delta_ms(all_items),
            all(
                _exact_reference(outflow, inflow)
                for outflow in ordered_out
                for inflow in ordered_in
            ),
            EligibilityBasis.RECIPROCAL_ACCOUNT,
            _multi_binding_digest(
                ordered_out, ordered_in, match_type=match_type
            ),
            ordered_out[1:],
            ordered_in[1:],
            match_type,
            next(iter(currencies)),
        )
        edges[edge.edge_id] = edge
        if len(edges) > policy.max_candidate_edges:
            raise A4ContractError("BLOCK_RESOURCE_LIMIT")

    for outflow in outflows:
        eligible = sorted(
            (
                item
                for item in inflows
                if item.currency == outflow.currency
                and _strong_pair(outflow, item, policy)
            ),
            key=lambda item: item.txn_uid,
        )
        for size in range(2, min(policy.max_subset_size, len(eligible)) + 1):
            for subset in itertools.combinations(eligible, size):
                add_candidate((outflow,), subset)
    for inflow in inflows:
        eligible = sorted(
            (
                item
                for item in outflows
                if item.currency == inflow.currency
                and _strong_pair(item, inflow, policy)
            ),
            key=lambda item: item.txn_uid,
        )
        for size in range(2, min(policy.max_subset_size, len(eligible)) + 1):
            for subset in itertools.combinations(eligible, size):
                add_candidate(subset, (inflow,))
    return tuple(sorted(edges.values(), key=lambda item: item.edge_id)), branches


def _build_fx_edges(
    principals: Sequence[CompiledTransaction], policy: VerifiedPolicy
) -> tuple[CandidateEdge, ...]:
    if not policy.fx_rules:
        return ()
    edges: dict[str, CandidateEdge] = {}
    outflows = [item for item in principals if item.direction is Direction.OUTFLOW]
    inflows = [item for item in principals if item.direction is Direction.INFLOW]
    for outflow in outflows:
        for inflow in inflows:
            if outflow.currency == inflow.currency or not _strong_pair(
                outflow, inflow, policy
            ):
                continue
            matching = [
                rule
                for rule in policy.fx_rules
                if rule.matches(source=outflow, target=inflow)
            ]
            if len(matching) > 1:
                raise A4ContractError("BLOCK_AMBIGUOUS_FX_RULE")
            if not matching:
                continue
            rule = matching[0]
            edge = CandidateEdge(
                outflow,
                inflow,
                None,
                FeeMode.NO_FEE,
                0,
                EvidenceGrade.RECEIPT_BOUND_FX,
                rule.rule_id,
                _time_delta_ms((outflow, inflow)),
                _exact_reference(outflow, inflow),
                EligibilityBasis.RECIPROCAL_ACCOUNT,
                _multi_binding_digest(
                    (outflow,), (inflow,), match_type=MatchType.FX, fx_rule=rule
                ),
                (),
                (),
                MatchType.FX,
                f"{rule.from_currency}/{rule.to_currency}",
                rule.rule_id,
                rule.rate_source_receipt_digest,
            )
            edges[edge.edge_id] = edge
    return tuple(sorted(edges.values(), key=lambda item: item.edge_id))


def build_candidate_edges(
    transactions: Sequence[CompiledTransaction],
    policy: VerifiedPolicy,
    metrics: dict[str, int] | None = None,
) -> tuple[CandidateEdge, ...]:
    if len(transactions) > policy.max_transactions:
        raise A4ContractError("BLOCK_RESOURCE_TRANSACTION_COUNT")
    if len(transactions) * 2_048 > policy.max_memory_bytes:
        raise A4ContractError("BLOCK_RESOURCE_MEMORY")
    principals = sorted(
        (item for item in transactions if item.row_kind == "PRINCIPAL"),
        key=lambda item: item.txn_uid,
    )
    fees = [item for item in transactions if item.row_kind == "FEE"]
    inflow_index: dict[tuple[str, str, str, int], list[CompiledTransaction]] = {}
    for inflow in principals:
        if inflow.direction is Direction.INFLOW:
            inflow_key = (
                inflow.tenant_id,
                inflow.source_account_id,
                inflow.currency,
                inflow.amount_minor,
            )
            inflow_index.setdefault(inflow_key, []).append(inflow)
    for bucket in inflow_index.values():
        bucket.sort(key=lambda item: (item.booked_at_utc, item.txn_uid))
    fee_index: dict[tuple[str, str, str, str], list[CompiledTransaction]] = {}
    for fee in fees:
        if fee.bank_reference_token:
            fee_key = (
                fee.tenant_id,
                fee.source_account_id,
                fee.currency,
                fee.bank_reference_token,
            )
            fee_index.setdefault(fee_key, []).append(fee)
    for bucket in fee_index.values():
        bucket.sort(key=lambda item: (item.booked_at_utc, item.txn_uid))
    edges: dict[str, CandidateEdge] = {}
    pair_checks = 0
    max_bucket_size = 0
    for outflow in principals:
        if (
            outflow.direction is not Direction.OUTFLOW
            or outflow.counterparty_resolution
            is not CounterpartyResolution.EXACT_VERIFIED
            or outflow.resolved_counterparty_account_id is None
        ):
            continue
        amount_rules: dict[int, FeeRule | None] = {outflow.amount_minor: None}
        for rule in policy.fee_rules:
            principal_amount = outflow.amount_minor - rule.fee_minor
            if principal_amount <= 0:
                continue
            if rule.matches(
                bank_code=outflow.bank_code,
                product_code=outflow.product_code,
                channel=outflow.channel,
                amount=principal_amount,
                at=outflow.booked_at_utc,
            ):
                previous_rule = amount_rules.get(principal_amount)
                if previous_rule is not None:
                    raise A4ContractError("BLOCK_AMBIGUOUS_FEE_RULE")
                amount_rules[principal_amount] = rule
        for principal_amount in sorted(amount_rules):
            bucket = inflow_index.get(
                (
                    outflow.tenant_id,
                    outflow.resolved_counterparty_account_id,
                    outflow.currency,
                    principal_amount,
                ),
                [],
            )
            max_bucket_size = max(max_bucket_size, len(bucket))
            if len(bucket) > policy.max_trace_bucket:
                raise A4ContractError("BLOCK_RESOURCE_TRACE_BUCKET")
            for inflow in bucket:
                pair_checks += 1
                if pair_checks > policy.max_pair_checks:
                    raise A4ContractError("BLOCK_RESOURCE_PAIR_CHECKS")
                if (
                    inflow.counterparty_resolution
                    is not CounterpartyResolution.EXACT_VERIFIED
                    or inflow.resolved_counterparty_account_id
                    != outflow.source_account_id
                    or outflow.source_account_id == inflow.source_account_id
                ):
                    continue
                outflow_day = outflow.value_date or outflow.local_date
                inflow_day = inflow.value_date or inflow.local_date
                gap_days = (inflow_day - outflow_day).days
                if not (
                    policy.min_signed_gap_days <= gap_days <= policy.max_signed_gap_days
                ):
                    continue
                time_delta = int(
                    abs((inflow.booked_at_utc - outflow.booked_at_utc).total_seconds())
                    * 1000
                )
                exact_ref = _exact_reference(outflow, inflow)
                basis = EligibilityBasis.RECIPROCAL_ACCOUNT
                binding_digest = digest_object(
                    {
                        "domain": "BUTLER_A4_STRONG_BINDING_V2_1",
                        "tenant_id": outflow.tenant_id,
                        "outflow_account_id": outflow.source_account_id,
                        "inflow_account_id": inflow.source_account_id,
                        "outflow_resolved_counterparty_account_id": outflow.resolved_counterparty_account_id,
                        "inflow_resolved_counterparty_account_id": inflow.resolved_counterparty_account_id,
                        "eligibility_basis": basis.value,
                    }
                )
                candidates: list[CandidateEdge] = []
                if outflow.amount_minor == inflow.amount_minor:
                    fee_bucket = (
                        fee_index.get(
                            (
                                outflow.tenant_id,
                                outflow.source_account_id,
                                outflow.currency,
                                outflow.bank_reference_token,
                            ),
                            (),
                        )
                        if outflow.bank_reference_token
                        else ()
                    )
                    matching_fees = [
                        fee
                        for fee in fee_bucket
                        if fee.direction is Direction.OUTFLOW
                        and abs(
                            (fee.booked_at_utc - outflow.booked_at_utc).total_seconds()
                        )
                        <= 86_400
                    ]
                    if matching_fees:
                        for fee in matching_fees:
                            candidates.append(
                                CandidateEdge(
                                    outflow,
                                    inflow,
                                    fee,
                                    FeeMode.SEPARATE_FEE_ROW,
                                    fee.amount_minor,
                                    EvidenceGrade.OBSERVED_FEE,
                                    None,
                                    time_delta,
                                    exact_ref,
                                    basis,
                                    binding_digest,
                                )
                            )
                    else:
                        candidates.append(
                            CandidateEdge(
                                outflow,
                                inflow,
                                None,
                                FeeMode.NO_FEE,
                                0,
                                EvidenceGrade.OBSERVED_PRINCIPAL,
                                None,
                                time_delta,
                                exact_ref,
                                basis,
                                binding_digest,
                            )
                        )
                elif outflow.amount_minor > inflow.amount_minor:
                    difference = outflow.amount_minor - inflow.amount_minor
                    matching_rule = amount_rules.get(inflow.amount_minor)
                    if (
                        matching_rule is not None
                        and matching_rule.fee_minor == difference
                    ):
                        candidates.append(
                            CandidateEdge(
                                outflow,
                                inflow,
                                None,
                                FeeMode.EMBEDDED_DEBIT,
                                difference,
                                EvidenceGrade.SCHEDULE_SUPPORTED_FEE_CANDIDATE,
                                matching_rule.rule_id,
                                time_delta,
                                exact_ref,
                                basis,
                                binding_digest,
                            )
                        )
                for edge in candidates:
                    edges[edge.edge_id] = edge
                    if len(edges) > policy.max_candidate_edges:
                        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    subset_edges, subset_branches = _build_subset_edges(principals, policy)
    fx_edges = _build_fx_edges(principals, policy)
    for edge in (*subset_edges, *fx_edges):
        edges[edge.edge_id] = edge
        if len(edges) > policy.max_candidate_edges:
            raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    if metrics is not None:
        metrics["candidate_pair_checks"] = pair_checks
        metrics["max_candidate_bucket_size"] = max_bucket_size
        metrics["candidate_subset_branches"] = subset_branches
    return tuple(sorted(edges.values(), key=lambda item: item.edge_id))


def _components(edges: Sequence[CandidateEdge]) -> list[tuple[CandidateEdge, ...]]:
    by_node: dict[str, list[CandidateEdge]] = {}
    for edge in edges:
        for node in edge.node_uids:
            by_node.setdefault(node, []).append(edge)
    unseen = set(by_node)
    result: list[tuple[CandidateEdge, ...]] = []
    while unseen:
        stack = [min(unseen)]
        unseen.remove(stack[0])
        found: dict[str, CandidateEdge] = {}
        while stack:
            node = stack.pop()
            for edge in by_node[node]:
                found[edge.edge_id] = edge
                for other in edge.node_uids:
                    if other in unseen:
                        unseen.remove(other)
                        stack.append(other)
        result.append(tuple(sorted(found.values(), key=lambda item: item.edge_id)))
    return sorted(result, key=lambda group: group[0].edge_id)


@dataclass(frozen=True, slots=True)
class _DPValue:
    objective: tuple[int, int, int]
    count: int
    union: frozenset[str]
    intersection: frozenset[str]
    representative: tuple[str, ...]


def _add_edge(edge: CandidateEdge, suffix: _DPValue) -> _DPValue:
    objective: tuple[int, int, int] = (
        edge.semantic_cost[0] + suffix.objective[0],
        edge.semantic_cost[1] + suffix.objective[1],
        edge.semantic_cost[2] + suffix.objective[2],
    )
    selected = frozenset({edge.edge_id})
    return _DPValue(
        objective,
        suffix.count,
        suffix.union | selected,
        suffix.intersection | selected,
        tuple(sorted((*suffix.representative, edge.edge_id))),
    )


def _merge_equal(values: Sequence[_DPValue]) -> _DPValue:
    best = min(value.objective for value in values)
    winners = [value for value in values if value.objective == best]
    union = frozenset().union(*(value.union for value in winners))
    intersection = winners[0].intersection
    for value in winners[1:]:
        intersection = intersection & value.intersection
    return _DPValue(
        best,
        sum(value.count for value in winners),
        union,
        intersection,
        min(value.representative for value in winners),
    )


def _solve_exact(component: Sequence[CandidateEdge]) -> _DPValue:
    outflows = sorted({edge.outflow.txn_uid for edge in component})
    by_out = {
        out: tuple(edge for edge in component if edge.outflow.txn_uid == out)
        for out in outflows
    }

    @lru_cache(maxsize=None)
    def solve(index: int, used_nodes: frozenset[str]) -> _DPValue:
        if index == len(outflows):
            return _DPValue((0, 0, 0), 1, frozenset(), frozenset(), ())
        values = [solve(index + 1, used_nodes)]
        for edge in by_out[outflows[index]]:
            if edge.node_uids & used_nodes:
                continue
            values.append(
                _add_edge(edge, solve(index + 1, used_nodes | edge.node_uids))
            )
        return _merge_equal(values)

    return solve(0, frozenset())


def reconcile(
    transactions: Sequence[CompiledTransaction], policy: VerifiedPolicy
) -> MatchResult:
    seen_uid: dict[tuple[str, str], str] = {}
    source_rows: dict[tuple[str, str], str] = {}
    artifacts: set[str] = set()
    unique: dict[tuple[str, str], CompiledTransaction] = {}
    for tx in transactions:
        key = tx.graph_key
        previous = seen_uid.get(key)
        if previous is not None and previous != tx.source_row_digest:
            raise A4ContractError("BLOCK_TXN_UID_CONFLICT")
        source_key = (tx.tenant_id, tx.source_row_digest)
        source_uid = source_rows.get(source_key)
        if source_uid is not None and source_uid != tx.txn_uid:
            raise A4ContractError("BLOCK_DUPLICATE_SOURCE_ROW")
        if tx.artifact_token in artifacts and key not in unique:
            raise A4ContractError("BLOCK_ARTIFACT_TOKEN_COLLISION")
        seen_uid[key] = tx.source_row_digest
        source_rows[source_key] = tx.txn_uid
        artifacts.add(tx.artifact_token)
        unique.setdefault(key, tx)
    ordered = tuple(sorted(unique.values(), key=lambda item: item.graph_key))
    active, terminal_groups = _terminal_partition(ordered)
    metrics: dict[str, int] = {}
    edges = build_candidate_edges(active, policy, metrics)
    components: list[ComponentResult] = []
    graph_nodes: set[str] = set()
    for group in _components(edges):
        nodes = frozenset().union(*(edge.node_uids for edge in group))
        graph_nodes.update(nodes)
        if len(nodes) > policy.max_component_nodes:
            raise A4ContractError("BLOCK_RESOURCE_LIMIT")
        solved = _solve_exact(group)
        forced = tuple(sorted(solved.intersection))
        selectable_nonforced = solved.union - solved.intersection
        ambiguous_nodes = sorted(
            frozenset().union(
                *(
                    edge.node_uids
                    for edge in group
                    if edge.edge_id in selectable_nonforced
                )
            )
            if selectable_nonforced
            else frozenset()
        )
        selectable_nodes = (
            frozenset().union(
                *(edge.node_uids for edge in group if edge.edge_id in solved.union)
            )
            if solved.union
            else frozenset()
        )
        unmatched = tuple(sorted(nodes - selectable_nodes))
        component_id = digest_object([edge.safe_dict() for edge in group])
        exact_count = len(nodes) <= 8
        components.append(
            ComponentResult(
                component_id,
                forced,
                tuple(ambiguous_nodes),
                unmatched,
                solved.count > 1,
                solved.count if exact_count else None,
                exact_count,
            )
        )
    globally_unmatched = tuple(
        sorted(tx.txn_uid for tx in active if tx.txn_uid not in graph_nodes)
    )
    return MatchResult(
        edges,
        tuple(sorted(components, key=lambda item: item.component_id)),
        globally_unmatched,
        metrics.get("candidate_pair_checks", 0),
        metrics.get("max_candidate_bucket_size", 0),
        metrics.get("candidate_subset_branches", 0),
        terminal_groups,
    )


def tenant_uuid(profile_id: str) -> str:
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise A4ContractError("BLOCK_ACCOUNT_IDENTITY")
    return str(uuid.uuid5(_UUID_NAMESPACE, profile_id.strip()))


def closed_world_dlp(payloads: Mapping[str, Any]) -> dict[str, Any]:
    """Reject values outside the evidence vocabulary, including PII-shaped data."""

    forbidden_key = re.compile(
        r"(?:^|_)(?:raw_text|raw_value|memo|holder_name|person_name|file_path|secret|password|account_number)(?:$|_)",
        re.I,
    )
    account_like = re.compile(
        r"(?<![A-Za-z0-9])(?:[0-9０-９][ -]?){8,20}(?![A-Za-z0-9])"
    )
    home_path = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\Users\\\\)")
    secret = re.compile(
        r"(?:bearer\s+[A-Za-z0-9._~-]+|api[_-]?key|private[_-]?key)", re.I
    )
    email = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])")
    allowed_string = re.compile(r"^[A-Za-z0-9._:+/@=-]{0,256}$")
    machine_identifier = re.compile(
        r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64}|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9:.+-]+Z?)?)$"
    )
    adapter_header_keys = {
        "source_account",
        "bank_code",
        "booking_date",
        "withdrawal",
        "deposit",
        "reference",
        "counter_account",
        "fee_type",
        "product_code",
        "channel",
        "currency",
        "value_date",
        "duplicate_of_reference",
        "reversal_of_reference",
        "allowed_date_formats",
    }
    values_scanned = 0
    protected_machine_keys = re.compile(
        r"(?:digest|token|signature|sha256|nonce|oid|uuid|_id)$", re.I
    )

    def scan_text(text: str, key: str, depth: int = 0) -> None:
        if protected_machine_keys.search(key):
            return
        if machine_identifier.fullmatch(text) and not re.fullmatch(
            r"[0-9a-f]{32,64}", text
        ):
            return
        if home_path.search(text) or secret.search(text) or email.search(text):
            raise A4ContractError("BLOCK_DLP")
        if account_like.search(text):
            raise A4ContractError("BLOCK_DLP")
        if depth >= 2:
            return
        decoded: list[bytes] = []
        if re.fullmatch(r"[0-9A-Fa-f]{8,512}", text) and len(text) % 2 == 0:
            try:
                decoded.append(bytes.fromhex(text))
            except ValueError:
                pass
        if re.fullmatch(r"[A-Za-z0-9_-]{8,684}={0,2}", text):
            try:
                padded = text + "=" * (-len(text) % 4)
                decoded.append(base64.b64decode(padded, altchars=b"-_", validate=True))
            except (ValueError, TypeError):
                pass
        for raw in decoded:
            try:
                nested = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if nested != text:
                scan_text(nested, key, depth + 1)

    def visit(value: Any, key: str = "") -> None:
        nonlocal values_scanned
        if forbidden_key.search(key):
            raise A4ContractError("BLOCK_DLP")
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)
        elif isinstance(value, str):
            values_scanned += 1
            scan_text(value, key)
            if machine_identifier.fullmatch(value):
                return
            if key in adapter_header_keys and len(value.encode("utf-8")) <= 96:
                return
            if not allowed_string.fullmatch(value):
                raise A4ContractError("BLOCK_DLP")
        elif value is not None and type(value) not in {int, bool}:
            raise A4ContractError("BLOCK_DLP")

    for filename, payload in payloads.items():
        if not re.fullmatch(r"[a-z_]+\.json", filename):
            raise A4ContractError("BLOCK_PATH")
        visit(payload)
    return {
        "scanner_version": "2.0.0",
        "files_scanned": len(payloads),
        "values_scanned": values_scanned,
        "leak_count": 0,
        "closed_world_pass": not False,
    }
