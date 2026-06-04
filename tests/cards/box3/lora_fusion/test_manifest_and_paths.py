from __future__ import annotations

from butler_pc_core.cards.box3.lora_fusion.constants import HELPER3_FORMAT_SHA256, HELPER5_TOOL_CALL_SHA256
from butler_pc_core.cards.box3.lora_fusion.fusion_paths import evaluate_runtime_lora_capability, validate_merge_to_gguf_plan
from butler_pc_core.cards.box3.lora_fusion.manifest import (
    FusionAdapterRef,
    FusionModelRef,
    FusionOutputModelRef,
    LoraFusionManifest,
    build_diagnosis_only_manifest,
    validate_lora_fusion_manifest,
)


def test_fusion_manifest_schema_diagnosis_only():
    manifest = build_diagnosis_only_manifest(diagnosis_status="ALREADY_FUSED_CONFIRMED")
    assert validate_lora_fusion_manifest(manifest) == []
    assert manifest.fusion_method == "already_fused"


def test_manifest_rejects_abbreviated_sha():
    manifest = {
        "schema_version": "box3.lora_fusion_manifest.v1",
        "diagnosis_status": "NOT_FUSED_CONFIRMED",
        "base_model": {"model_choice": "m", "sha256_full": "60b9baee", "model_path_ref": "ref:MODEL", "readonly_verified": True},
        "adapters": [],
        "fusion_method": "runtime_lora",
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    errors = validate_lora_fusion_manifest(manifest)
    assert "BASE_MODEL_SHA_INVALID" in errors
    assert "ADAPTERS_INVALID" in errors


def test_runtime_lora_partial_when_multi_adapter_unproven():
    verdict = evaluate_runtime_lora_capability(
        lora_path_supported=True,
        multi_lora_api_smoke_pass=False,
        helper3_loaded=True,
        helper5_loaded=False,
    )
    assert verdict.supported is False
    assert verdict.fail_class == "PARTIAL_MULTI_LORA_UNPROVEN"


def test_runtime_lora_supported_when_all_probe_passes():
    verdict = evaluate_runtime_lora_capability(
        lora_path_supported=True,
        multi_lora_api_smoke_pass=True,
        helper3_loaded=True,
        helper5_loaded=True,
    )
    assert verdict.supported is True
    assert verdict.fail_class is None


def test_merge_to_gguf_requires_sources_and_quant():
    verdict = validate_merge_to_gguf_plan(
        base_sha256_full="1" * 64,
        helper3_sha256_full=HELPER3_FORMAT_SHA256,
        helper5_sha256_full=HELPER5_TOOL_CALL_SHA256,
        output_sha256_full="2" * 64,
        size_bytes=3_000_000_000,
        quant_config={"quantization": "q4_k_m", "toolchain": "llama.cpp"},
    )
    assert verdict.produced is True
    assert verdict.status == "FUSION_PRODUCED"
    assert verdict.general_pc_candidate is True


def test_merge_to_gguf_blocks_general_pc_budget_excess():
    verdict = validate_merge_to_gguf_plan(
        base_sha256_full="1" * 64,
        helper3_sha256_full=HELPER3_FORMAT_SHA256,
        helper5_sha256_full=HELPER5_TOOL_CALL_SHA256,
        output_sha256_full="2" * 64,
        size_bytes=9_000_000_000,
        quant_config={"quantization": "q4_k_m"},
    )
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_GENERAL_PC_BUDGET_EXCEEDED"
