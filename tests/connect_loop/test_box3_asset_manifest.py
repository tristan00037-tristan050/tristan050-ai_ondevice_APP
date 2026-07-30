from butler_pc_core.cards.box3.asset_manifest import (
    ASSET_INVENTORY_PASS_STATUS,
    Box3AssetRecord,
    HELPER3_SHA,
    HELPER4_SHA,
    HELPER7_SHA,
    HELPER8_SHA,
    build_contract_only_asset_manifest,
    build_real_asset_manifest,
    is_full_sha256,
    manifest_allows_real,
    validate_asset_record,
)


def test_asset_manifest_requires_full_sha_for_real_claim():
    record = Box3AssetRecord(
        asset_name="helper4_grounding",
        role="grounding",
        display_sha_prefix="b7b1af0e...",
        asset_path="/runtime-only/path",
        sha256_full="b7b1af0e",
        sha_scope="file",
        measured_at="2026-06-01T00:00:00+00:00",
        measured_by="test",
        source_metadata_files=[],
        interface_inventory_status="pass",
        real_claim_allowed=True,
        fail_class=None,
    )
    assert "FULL_SHA_REQUIRED_FOR_REAL" in validate_asset_record(record)
    assert "SHORT_OR_INVALID_SHA_FORBIDDEN" in validate_asset_record(record)


def test_contract_only_manifest_is_honest_partial_not_real():
    manifest = build_contract_only_asset_manifest(measured_at="2026-06-01T00:00:00+00:00")
    assert manifest["status"] == "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING"
    assert manifest["real_claim_allowed"] is False
    assert manifest["state_gate"] == "CONTRACT_ONLY"
    assert manifest_allows_real(manifest) is False
    helper3 = next(item for item in manifest["assets"] if item["asset_name"] == "helper3_format")
    assert helper3["sha256_full"] == HELPER3_SHA
    assert is_full_sha256(helper3["sha256_full"])
    assert helper3["real_claim_allowed"] is False
    helper4 = next(item for item in manifest["assets"] if item["asset_name"] == "helper4_grounding")
    assert helper4["sha256_full"] == HELPER4_SHA
    assert is_full_sha256(helper4["sha256_full"])
    assert helper4["real_claim_allowed"] is False
    assert helper4["fail_class"] == "INTERFACE_INVENTORY_PENDING"
    helper8 = next(item for item in manifest["assets"] if item["asset_name"] == "helper8_company_style")
    assert helper8["sha256_full"] == HELPER8_SHA
    assert is_full_sha256(helper8["sha256_full"])
    assert helper8["real_claim_allowed"] is False
    assert helper8["fail_class"] == "INTERFACE_INVENTORY_PENDING"
    helper7 = next(item for item in manifest["assets"] if item["asset_name"] == "helper7_table_figure")
    assert helper7["sha256_full"] == HELPER7_SHA
    assert helper7["asset_path"] is None
    assert helper7["real_claim_allowed"] is False


def test_real_asset_manifest_without_central_receipt_remains_contract_only():
    manifest = build_real_asset_manifest(measured_at="2026-06-03T00:00:00+00:00")
    assert manifest["status"] == "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING"
    assert manifest["real_claim_allowed"] is False
    assert manifest_allows_real(manifest) is False
