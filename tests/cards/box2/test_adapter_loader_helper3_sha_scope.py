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


def test_helper_3_contract_path_targets_measured_file():
    """Follow-on P1 (Codex re-review on 3e9e7c60): sha_scope='file' alone is
    insufficient — the contract path must resolve to the actual file whose
    SHA was sealed. Otherwise compute_sha_for_contract() returns None when
    the path is a directory and check_asset() still emits
    PARTIAL_DONE_V2_SHA_SCOPE_PENDING, so a tampered helper_3 never raises
    BLOCK_V2_SHA_MISMATCH.

    Evidence: evidence/box2_helper3/sha_contract_v2.json L10 — the sealed
    measured_file_path is .../box2b_v5_rewrite/adapter_model.safetensors.
    """
    contracts = a.asset_contracts()
    assert contracts["helper_3"].path.endswith("/adapter_model.safetensors"), (
        "helper_3 contract path must target adapter_model.safetensors to enable file SHA verification"
    )
    assert contracts["helper_3"].path_kind == "file", (
        "helper_3 path_kind must be 'file' so kind_matches requires path.is_file()"
    )
    # The public DEFAULT_HELPER_3_PATH constant is preserved as the adapter
    # directory for status/evidence parity — the file-pointing path lives
    # only in the AssetContract.
    assert a.DEFAULT_HELPER_3_PATH.endswith("/box2b_v5_rewrite")
    assert contracts["helper_3"].path.startswith(a.DEFAULT_HELPER_3_PATH + "/")


def test_helper_3_tampered_file_would_raise_block_sha_mismatch(tmp_path, monkeypatch):
    """End-to-end tamper detection: with the path targeting a file and
    sha_scope='file', a wrong-content file at the contract path produces
    BLOCK_V2_SHA_MISMATCH (not PARTIAL_DONE_V2_SHA_SCOPE_PENDING)."""
    fake_root = tmp_path / "handoff"
    fake_dir = fake_root / "box2b_v5_outputs/rewrite/adapter/box2b_v5_rewrite"
    fake_dir.mkdir(parents=True)
    tampered = fake_dir / "adapter_model.safetensors"
    tampered.write_bytes(b"tampered weights - not the real adapter")

    # Repoint the contract path constant chain at our temp tree.
    monkeypatch.setattr(a, "DEFAULT_HANDOFF_ROOT", str(fake_root))
    monkeypatch.setattr(
        a, "DEFAULT_HELPER_3_PATH",
        str(fake_dir),
    )

    contracts = a.asset_contracts()
    check = a.check_asset(contracts["helper_3"], allow_missing=False)
    assert check.status == "BLOCK_V2_SHA_MISMATCH", (
        f"tamper detection regressed: expected BLOCK_V2_SHA_MISMATCH, got {check.status} "
        f"(sha_checked={check.sha_checked}, actual={check.actual_sha256})"
    )
    assert check.sha_checked is True
    assert check.sha_match is False
