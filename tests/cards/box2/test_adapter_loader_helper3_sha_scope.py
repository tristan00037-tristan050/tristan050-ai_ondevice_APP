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
    assert a.DEFAULT_HELPER_3_PATH == "asset://box2.adapter/rewrite_adapter"
    assert contracts["helper_3"].path.startswith(a.DEFAULT_HELPER_3_PATH + "/")


def test_helper_3_arbitrary_path_override_cannot_bypass_central_service(monkeypatch):
    class MissingService:
        @staticmethod
        def require_capability(_capability):
            from butler_pc_core.assets.errors import AssetError

            raise AssetError("REQUIRED_ASSET_MISSING")

    monkeypatch.setattr(a, "get_asset_service", lambda: MissingService())
    contracts = a.asset_contracts()
    check = a.check_asset(contracts["helper_3"], allow_missing=False)
    assert check.status == "BLOCK_ASSET_PATH_MISSING"
    assert check.sha_checked is False
    assert check.actual_sha256 is None
