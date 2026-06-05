"""ALG v5 canonical constants 정합 (PR #783, 2026-06-05) — MAINDEV
``actual_runner_assets`` + ``v5_asset_manifest`` SSOT 위에서 v5 상수와 lineage 의
무결성을 잠근다. 단일 경로 — ALG 별도 모듈 없이 MAINDEV API 만 사용.
"""
from __future__ import annotations

from butler_pc_core.cards.box3 import actual_runner_assets as assets


def test_v5_constants_replace_v4_default():
    assert assets.BASE_MODEL_NAME == "butler-1.7b-v5-q4_k_m.gguf"
    assert assets.BASE_MODEL_SHA256_FULL == (
        "5e233aab773d0cdb2b188649edbd36633f3dbb58be7ff4c4295a83de648212d2"
    )
    assert assets.BASE_MODEL_F16_SHA256_FULL == (
        "9594280709d47ffc48b5e0e69e9b3d3f77589991f9950749db1955761042fc37"
    )
    assert "v4" not in assets.BASE_MODEL_NAME
    assert assets.MODEL_LINEAGE["merge_method"] == "linear"
    assert assets.MODEL_LINEAGE["weights"] == [0.5, 0.4, 0.4]
    assert assets.MODEL_LINEAGE["included_adapters"] == [
        "butler_v3",
        "helper3_format",
        "helper5_tool_call",
    ]
    assert assets.MODEL_LINEAGE["runtime_lora_stack_allowed"] is False


def test_v5_size_bytes_and_historical_v4_reference_only():
    assert assets.BASE_MODEL_SIZE_BYTES == 1_073_741_824
    # v4 SHA 는 historical reference 만 — operational default 0.
    assert assets.V4_RT_SHA256_HISTORICAL_REFERENCE_ONLY == (
        "60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f"
    )


def test_helper3_5_are_embedded_in_v5_base_model_rows():
    rows = {row["asset_name"]: row for row in assets.build_helper_asset_rows()}
    assert rows["helper3_format"]["component_type"] == "embedded_model_adapter"
    assert rows["helper5_tool_call"]["component_type"] == "embedded_model_adapter"
    assert rows["helper3_format"]["runtime_lora_stack_allowed"] is False
    assert rows["helper5_tool_call"]["runtime_lora_stack_allowed"] is False
    # helper4/7/8 는 SDK module 로 분리 (model stack 에 끼지 않음).
    assert rows["helper4_grounding"]["component_type"] == "sdk_module"
    assert rows["helper7_table_figure"]["component_type"] == "sdk_module"
    assert rows["helper8_company_style"]["component_type"] == "sdk_module"


def test_v5_manifest_digest_is_digest_only():
    from butler_pc_core.cards.box3.v5_asset_manifest import build_v5_asset_manifest

    manifest = build_v5_asset_manifest().to_dict()
    digest = assets.v5_manifest_digest(manifest)
    assert digest.startswith("sha256:") and len(digest) == 71
    # production claim 은 v5 단계에서 닫혀있어야 한다 (단일 PR 검토 한정).
    assert manifest["model_lineage"]["production_claim_allowed"] is False
    assert manifest["raw_saved_zero"] is True
    assert manifest["external_send_zero"] is True
