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
    # 박스 3 real asset 재시도 (2026-06-03, 9도우미 zip 봉인 패키지 실측):
    # helper4·helper8 실측 SHA 반영, helper7 만 PENDING.
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
    missing = [item for item in manifest["assets"] if item["sha256_full"] is None]
    assert {item["asset_name"] for item in missing} == {"helper7_table_figure"}


def test_real_asset_manifest_inventory_pass_allows_real():
    """박스 3 real asset 최종 — 9도우미 4 helper 실측 PASS → ASSET_INVENTORY_PASS."""
    manifest = build_real_asset_manifest(measured_at="2026-06-03T00:00:00+00:00")
    assert manifest["status"] == ASSET_INVENTORY_PASS_STATUS
    assert manifest["state_gate"] == ASSET_INVENTORY_PASS_STATUS
    assert manifest["real_claim_allowed"] is True
    assert manifest_allows_real(manifest) is True
    expected = {
        "helper3_format": HELPER3_SHA,
        "helper4_grounding": HELPER4_SHA,
        "helper7_table_figure": HELPER7_SHA,
        "helper8_company_style": HELPER8_SHA,
    }
    for item in manifest["assets"]:
        assert item["sha256_full"] == expected[item["asset_name"]]
        assert is_full_sha256(item["sha256_full"])
        assert item["sha_scope"] == "file"
        assert item["interface_inventory_status"] == "pass"
        assert item["real_claim_allowed"] is True
        assert item["fail_class"] is None
    # asset_errors 4 helper 모두 빈 list (검증 통과).
    assert all(errs == [] for errs in manifest["asset_errors"].values())
