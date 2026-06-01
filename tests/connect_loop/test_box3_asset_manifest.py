from butler_pc_core.cards.box3.asset_manifest import (
    Box3AssetRecord,
    HELPER3_SHA,
    build_contract_only_asset_manifest,
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
    missing = [item for item in manifest["assets"] if item["sha256_full"] is None]
    assert {item["asset_name"] for item in missing} == {
        "helper4_grounding",
        "helper7_table_figure",
        "helper8_company_style",
    }

