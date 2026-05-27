"""Regression guard for Codex P1 #1 (PR #754, 2026-05-25)."""

from butler_pc_core.cards.box2 import adapter_loader as a


def test_helper_3_sha_scope_is_not_unknown():
    contracts = a.asset_contracts()
    assert contracts["helper_3"].sha_scope != "unknown", (
        "helper_3 sha_scope='unknown' regressed — Codex P1 #1 defect re-introduced"
    )


def test_helper_3_sha_scope_enables_digest_computation():
    contracts = a.asset_contracts()
    valid_scopes_with_digest = {"file", "directory_manifest"}
    assert contracts["helper_3"].sha_scope in valid_scopes_with_digest


def test_helper_3_sha_scope_matches_sealed_evidence_file_scope():
    contracts = a.asset_contracts()
    assert contracts["helper_3"].sha_scope == "file"
    assert contracts["helper_3"].expected_sha256 == a.HELPER_3_REWRITE_ADAPTER_SHA
    assert len(a.HELPER_3_REWRITE_ADAPTER_SHA) == 64
    assert all(c in "0123456789abcdef" for c in a.HELPER_3_REWRITE_ADAPTER_SHA)


def test_helper_3_contract_path_targets_measured_file():
    contracts = a.asset_contracts()
    assert contracts["helper_3"].path.endswith("/adapter_model.safetensors"), (
        "helper_3 contract path must target adapter_model.safetensors to enable file SHA verification"
    )
    assert contracts["helper_3"].path_kind == "file", (
        "helper_3 path_kind must be 'file' so kind_matches requires path.is_file()"
    )
    assert a.DEFAULT_HELPER_3_PATH.endswith("/box2b_v5_rewrite")
    assert contracts["helper_3"].path.startswith(a.DEFAULT_HELPER_3_PATH + "/")


def test_helper_3_tampered_file_would_raise_block_sha_mismatch(tmp_path, monkeypatch):
    fake_root = tmp_path / "handoff"
    fake_dir = fake_root / "box2b_v5_outputs/rewrite/adapter/box2b_v5_rewrite"
    fake_dir.mkdir(parents=True)
    tampered = fake_dir / "adapter_model.safetensors"
    tampered.write_bytes(b"tampered weights - not the real adapter")

    monkeypatch.setattr(a, "DEFAULT_HANDOFF_ROOT", str(fake_root))
    monkeypatch.setattr(a, "DEFAULT_HELPER_3_PATH", str(fake_dir))

    contracts = a.asset_contracts()
    check = a.check_asset(contracts["helper_3"], allow_missing=False)
    assert check.status == "BLOCK_V2_SHA_MISMATCH", (
        f"tamper detection regressed: expected BLOCK_V2_SHA_MISMATCH, got {check.status} "
        f"(sha_checked={check.sha_checked}, actual={check.actual_sha256})"
    )
    assert check.sha_checked is True
    assert check.sha_match is False
