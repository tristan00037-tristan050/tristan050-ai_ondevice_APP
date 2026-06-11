"""ALG v5 canonical constants 정합 (PR #783, 2026-06-05; PR #787 v7 전환 정정 2026-06-07).

v9.1 canonical apply 후 v5 는 historical reference 로 격리 — 본 테스트는 v5
상수가 ``actual_runner_assets`` 의 `V5_*_HISTORICAL_REFERENCE_ONLY` 상수 + 별도
`v5_asset_manifest` 모듈에 그대로 보존되었음을 잠근다 (회귀 0). 운영 default 는 v9.1.
"""
from __future__ import annotations

from butler_pc_core.cards.box3 import actual_runner_assets as assets


def test_v5_constants_preserved_as_historical_reference_only():
    # v9.1 operational default 0 검증: 현재 BASE_MODEL_* 는 v9.1 정본.
    assert assets.BASE_MODEL_NAME == "butler-1.7b-v9-2-r2b-q4_k_m.gguf"
    assert "v5" not in assets.BASE_MODEL_NAME
    # v5 상수는 historical 라벨로만 보존 — 운영 default 어디에도 사용 0.
    assert assets.V5_BASE_MODEL_NAME_HISTORICAL_REFERENCE_ONLY == (
        "butler-1.7b-v5-q4_k_m.gguf"
    )
    assert assets.V5_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY == (
        "5e233aab773d0cdb2b188649edbd36633f3dbb58be7ff4c4295a83de648212d2"
    )
    assert assets.V5_F16_SHA256_HISTORICAL_REFERENCE_ONLY == (
        "9594280709d47ffc48b5e0e69e9b3d3f77589991f9950749db1955761042fc37"
    )
    # v5 lineage (linear merge, weights 0.5/0.4/0.4) 도 historical 보존.
    lineage = assets.V5_MODEL_LINEAGE_HISTORICAL_REFERENCE_ONLY
    assert lineage["merge_method"] == "linear"
    assert lineage["weights"] == [0.5, 0.4, 0.4]
    assert lineage["included_adapters"] == [
        "butler_v3", "helper3_format", "helper5_tool_call",
    ]
    assert lineage["runtime_lora_stack_allowed"] is False


def test_v5_size_bytes_and_historical_v4_reference_only():
    # v5 size historical
    assert assets.V5_BASE_MODEL_SIZE_BYTES_HISTORICAL_REFERENCE_ONLY == 1_073_741_824
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
    # v7 전환 후 v5 manifest 는 historical 모듈에서 직접 빌드 + actual_contracts 의
    # stable_json_digest 로 digest 측정 (격리된 historical 영수증).
    from butler_pc_core.cards.box3.actual_contracts import stable_json_digest
    from butler_pc_core.cards.box3.v5_asset_manifest import build_v5_asset_manifest

    manifest = build_v5_asset_manifest().to_dict()
    digest = stable_json_digest(manifest)
    assert digest.startswith("sha256:") and len(digest) == 71
    assert manifest["model_lineage"]["production_claim_allowed"] is False
    assert manifest["raw_saved_zero"] is True
    assert manifest["external_send_zero"] is True
