"""Regression guard for Codex P1 #1 (PR #754, 2026-05-25).

helper_3 was configured with a full expected_sha256 but sha_scope="unknown",
so check_asset() could not compute an actual digest and returned
PARTIAL_DONE_V2_SHA_SCOPE_PENDING instead of validating integrity. A modified
helper_3 artifact would never have raised BLOCK_V2_SHA_MISMATCH, undermining
tamper detection for one of the three model-chain assets.
"""

from butler_pc_core.cards.box2 import adapter_loader as a


def test_helper_3_sha_scope_is_not_unknown():
    contracts = a.asset_contracts()
    assert contracts["helper_3"].sha_scope != "unknown", (
        "helper_3 sha_scope='unknown' regressed — Codex P1 #1 defect re-introduced"
    )


def test_helper_3_sha_scope_enables_digest_computation():
    contracts = a.asset_contracts()
    valid_scopes_with_digest = {"file", "directory_manifest"}
    assert contracts["helper_3"].sha_scope in valid_scopes_with_digest, (
        f"helper_3 sha_scope must be a scope that produces a digest in "
        f"compute_sha_for_contract; got {contracts['helper_3'].sha_scope!r}"
    )


def test_helper_3_sha_scope_matches_sealed_evidence_file_scope():
    """sha_scope must equal the measured_sha_scope sealed in sha_contract_v2.json.

    evidence/box2_helper3/sha_contract_v2.json L8-11 seals
    sha_scope=file and measured_sha256_file == HELPER_3_REWRITE_ADAPTER_SHA,
    so the Python contract must declare the same scope.
    """
    contracts = a.asset_contracts()
    assert contracts["helper_3"].sha_scope == "file"
    assert contracts["helper_3"].expected_sha256 == a.HELPER_3_REWRITE_ADAPTER_SHA
    assert len(a.HELPER_3_REWRITE_ADAPTER_SHA) == 64
    assert all(c in "0123456789abcdef" for c in a.HELPER_3_REWRITE_ADAPTER_SHA)
