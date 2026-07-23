from __future__ import annotations

import ast
from pathlib import Path

from butler_pc_core.accounting.classify.reconciliation_service_v2 import (
    VERIFIER_TOKEN_KEY_FIELDS,
)


def test_v55_verifier_key_material_contract_is_exact() -> None:
    assert VERIFIER_TOKEN_KEY_FIELDS == {
        "schema_version",
        "tenant_id",
        "key_id",
        "own_account_key_b64",
        "bank_reference_key_b64",
        "counterparty_account_key_b64",
        "run_transaction_key_b64",
    }
    assert "verification_signing_seed_b64" not in VERIFIER_TOKEN_KEY_FIELDS


def test_v55_producer_and_independent_verifier_both_reject_extra_key_fields() -> None:
    root = Path(__file__).resolve().parents[3]
    producer = ast.parse(
        (root / "butler_pc_core/accounting/classify/reconciliation_service_v2.py").read_text(
            encoding="utf-8"
        )
    )
    verifier = ast.parse(
        (root / "butler_pc_core/a4_verifier/cli.py").read_text(encoding="utf-8")
    )
    producer_source = ast.unparse(producer)
    verifier_source = ast.unparse(verifier)
    assert "set(material) != VERIFIER_TOKEN_KEY_FIELDS" in producer_source
    assert "'verification_signing_seed_b64' in material" in producer_source
    assert "set(material) != required" in verifier_source
    assert "block('BLOCK_TRUST_UNAVAILABLE')" in verifier_source
