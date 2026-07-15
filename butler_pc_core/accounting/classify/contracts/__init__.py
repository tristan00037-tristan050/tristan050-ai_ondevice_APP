"""Box5 stage-3 contract closure (F005 reason registry · F006 canonical tx schema · F015 receipt schema).

Area A (policy) and Area B (classifier) meet only through these signed-shape contracts,
never by importing each other. This subpackage is pure-stdlib + jsonschema (validation only);
it does not post journals and JOURNAL_AUTO_POST_ALLOWED stays NO.
"""

from .registry import (
    ReasonRegistryError,
    REASON_REGISTRY_CODES,
    registry_closure_digest,
    emit_reason,
    to_canonical_mapping,
    canonical_transaction_digest,
    validate_canonical_transaction,
    validate_decision_receipt,
    build_decision_receipt,
)

__all__ = [
    "ReasonRegistryError",
    "REASON_REGISTRY_CODES",
    "registry_closure_digest",
    "emit_reason",
    "to_canonical_mapping",
    "canonical_transaction_digest",
    "validate_canonical_transaction",
    "validate_decision_receipt",
    "build_decision_receipt",
]
