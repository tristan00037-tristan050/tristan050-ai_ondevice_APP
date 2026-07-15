"""Signed-shape closure for the stage-3 classifier contract.

F005 — the reason values a draft can carry are pinned to reason_codes.registry.csv, and the
       classifier may not emit a reason outside it (no free strings). The registry closure
       digest is bound into every decision receipt.
F006 — a CanonicalTransactionV2 has a fixed JSON Schema and an RFC 8785 (JCS) digest so Area A
       and Area B provably see the same transaction.
F015 — a decision receipt is validated against a schema whose conditional invariants make a
       contradictory AUTO_PROPOSE (null account, blocker present, out-of-registry reason,
       carried warning) unrepresentable.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import jsonschema

from butler_pc_core.accounting.classify.models import (
    CanonicalTransactionV2,
    ReasonCode,
    UnverifiedClassificationDraft,
)

_HERE = Path(__file__).resolve().parent
_REGISTRY_CSV = _HERE / "reason_codes.registry.csv"
_CANONICAL_TX_SCHEMA = _HERE / "canonical_transaction.v1.schema.json"
_RECEIPT_SCHEMA = _HERE / "decision_receipt.v1.schema.json"

# AC-006 classifier-contract fail code — must be registered even though it is not a ReasonCode.
_AC006_FAIL_CODE = "BLOCK_CLASSIFIER_CONTRACT"


class ReasonRegistryError(ValueError):
    """A reason or receipt escaped the signed registry/schema closure."""


def _load_registry_codes() -> frozenset[str]:
    try:
        with _REGISTRY_CSV.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:  # pragma: no cover
        raise ReasonRegistryError("REASON_REGISTRY_UNREADABLE") from exc
    codes = [str(row["code"]).strip() for row in rows if row.get("code")]
    if len(codes) != len(set(codes)):
        raise ReasonRegistryError("REASON_REGISTRY_DUPLICATE")
    return frozenset(codes)


REASON_REGISTRY_CODES: frozenset[str] = _load_registry_codes()

# F005 closure: every ReasonCode the code can produce, and the AC-006 fail code, must be
# registered. A drift (code value not in the signed registry) fails closed at import time.
_missing = {r.value for r in ReasonCode} - REASON_REGISTRY_CODES
if _missing:
    raise ReasonRegistryError(f"REASON_CODE_NOT_IN_REGISTRY:{','.join(sorted(_missing))}")
if _AC006_FAIL_CODE not in REASON_REGISTRY_CODES:
    raise ReasonRegistryError("AC006_FAIL_CODE_NOT_IN_REGISTRY")


def registry_closure_digest() -> str:
    """Deterministic digest binding the exact registered reason set to a receipt."""
    payload = json.dumps(sorted(REASON_REGISTRY_CODES), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def emit_reason(reason: str) -> ReasonCode:
    """F005: return a ReasonCode only if the value is in the signed registry; else fail closed."""
    if reason not in REASON_REGISTRY_CODES:
        raise ReasonRegistryError("REASON_NOT_IN_REGISTRY")
    return ReasonCode(reason)


def _jcs(value: Any) -> str:
    """RFC 8785 canonicalization for the transaction shape (strings/ints/arrays/null only)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def to_canonical_mapping(tx: CanonicalTransactionV2) -> dict[str, Any]:
    """Wire-shaped, schema-valid dict view of a canonical transaction (dates as ISO strings)."""
    def _d(value: date | None) -> str | None:
        return None if value is None else value.isoformat()

    mapping: dict[str, Any] = {
        "schema_version": tx.schema_version,
        "tenant_id": tx.tenant_id,
        "company_id": tx.company_id,
        "request_id": tx.request_id,
        "transaction_id": tx.transaction_id,
        "source_bank_id": tx.source_bank_id,
        "booked_date": _d(tx.booked_date),
        "value_date": _d(tx.value_date),
        "direction": tx.direction.value,
        "amount_minor": tx.amount_minor,
        "currency": tx.currency,
        "currency_registry_version": tx.currency_registry_version,
        "transaction_digest": tx.transaction_digest,
        "source_record_digest": tx.source_record_digest,
        "counterparty_account_token": tx.counterparty_account_token,
        "vendor_token": tx.vendor_token,
        "purpose_code": tx.purpose_code,
        "purpose_evidence_digest": tx.purpose_evidence_digest,
        "description_feature_digests": list(tx.description_feature_digests),
        "evidence_digests": list(tx.evidence_digests),
        "service_period_start": _d(tx.service_period_start),
        "service_period_end": _d(tx.service_period_end),
        "accounting_period_end": _d(tx.accounting_period_end),
        "event_kind": tx.event_kind.value,
        "original_transaction_digest": tx.original_transaction_digest,
        "adjustment_reason_code": tx.adjustment_reason_code,
    }
    return mapping


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_canonical_transaction(mapping: Mapping[str, Any]) -> None:
    """F006: reject any transaction that does not fit the canonical wire schema."""
    try:
        jsonschema.validate(dict(mapping), _load_schema(_CANONICAL_TX_SCHEMA))
    except jsonschema.ValidationError as exc:
        raise ReasonRegistryError(f"CANONICAL_TRANSACTION_SCHEMA_INVALID:{exc.message}") from None


def canonical_transaction_digest(tx: CanonicalTransactionV2) -> str:
    """F006: schema-validated RFC 8785 digest binding both areas to the same transaction."""
    mapping = to_canonical_mapping(tx)
    validate_canonical_transaction(mapping)
    return hashlib.sha256(_jcs(mapping).encode("utf-8")).hexdigest()


def validate_decision_receipt(receipt: Mapping[str, Any]) -> None:
    """F015: reject any receipt that violates the conditional-invariant schema."""
    try:
        jsonschema.validate(dict(receipt), _load_schema(_RECEIPT_SCHEMA))
    except jsonschema.ValidationError as exc:
        raise ReasonRegistryError(f"DECISION_RECEIPT_SCHEMA_INVALID:{exc.message}") from None


def build_decision_receipt(
    draft: UnverifiedClassificationDraft, tx: CanonicalTransactionV2
) -> dict[str, Any]:
    """Build the schema-valid stage-3 receipt binding tx canonical digest + registry closure.

    Never a posting authority: journal_auto_post_allowed is pinned False.
    """
    if draft.transaction_digest != tx.transaction_digest:
        raise ReasonRegistryError("RECEIPT_TRANSACTION_MISMATCH")
    payload = draft.to_finalize_payload()
    payload.update(
        {
            "transaction_canonical_digest": canonical_transaction_digest(tx),
            "reason_registry_closure_digest": registry_closure_digest(),
            "journal_auto_post_allowed": False,
        }
    )
    validate_decision_receipt(payload)
    return payload
