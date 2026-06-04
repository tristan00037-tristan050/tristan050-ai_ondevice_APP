from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .constants import (
    FAIL_BLOCK_GENERAL_PC_BUDGET_EXCEEDED,
    FAIL_BLOCK_INPUT_SHA_MISMATCH,
    FAIL_BLOCK_QUANT_CONFIG_MISMATCH,
    FAIL_PARTIAL_MERGE_SOURCE_MISSING,
    FAIL_PARTIAL_MULTI_LORA_UNPROVEN,
    FAIL_PARTIAL_RUNTIME_LORA_UNSUPPORTED,
    GENERAL_PC_LIMITS,
    MODEL_ADAPTER_HELPERS,
)
from .security import assert_no_raw_or_path_material, is_bare_sha256, stable_json_digest


@dataclass(frozen=True)
class RuntimeLoraCapabilityVerdict:
    method: Literal["runtime_lora"]
    supported: bool
    status: Literal["SUPPORTED", "PARTIAL"]
    fail_class: str | None
    multi_lora_proven: bool
    lora_path_supported: bool
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_raw_or_path_material(payload)
        return payload


def evaluate_runtime_lora_capability(
    *,
    lora_path_supported: bool,
    multi_lora_api_smoke_pass: bool,
    helper3_loaded: bool,
    helper5_loaded: bool,
) -> RuntimeLoraCapabilityVerdict:
    core = {
        "lora_path_supported": lora_path_supported,
        "multi_lora_api_smoke_pass": multi_lora_api_smoke_pass,
        "helper3_loaded": helper3_loaded,
        "helper5_loaded": helper5_loaded,
    }
    if not lora_path_supported:
        return RuntimeLoraCapabilityVerdict("runtime_lora", False, "PARTIAL", FAIL_PARTIAL_RUNTIME_LORA_UNSUPPORTED, False, False, stable_json_digest(core))
    if not (multi_lora_api_smoke_pass and helper3_loaded and helper5_loaded):
        return RuntimeLoraCapabilityVerdict("runtime_lora", False, "PARTIAL", FAIL_PARTIAL_MULTI_LORA_UNPROVEN, False, True, stable_json_digest(core))
    return RuntimeLoraCapabilityVerdict("runtime_lora", True, "SUPPORTED", None, True, True, stable_json_digest(core))


@dataclass(frozen=True)
class MergeToGgufPlanVerdict:
    method: Literal["merge_to_gguf"]
    produced: bool
    status: Literal["FUSION_PRODUCED", "PARTIAL", "BLOCKED"]
    fail_class: str | None
    input_digest: str
    output_digest: str | None
    size_bytes: int | None
    quant_config_digest: str | None
    general_pc_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_raw_or_path_material(payload)
        return payload


def validate_merge_to_gguf_plan(
    *,
    base_sha256_full: str | None,
    helper3_sha256_full: str | None,
    helper5_sha256_full: str | None,
    output_sha256_full: str | None,
    size_bytes: int | None,
    quant_config: dict[str, Any] | None,
    peak_rss_mb: int | None = None,
    latency_ms: int | None = None,
) -> MergeToGgufPlanVerdict:
    core = {
        "base": base_sha256_full,
        "helper3": helper3_sha256_full,
        "helper5": helper5_sha256_full,
        "quant_config": quant_config,
    }
    input_digest = stable_json_digest(core)

    if not (is_bare_sha256(base_sha256_full) and helper3_sha256_full == MODEL_ADAPTER_HELPERS["helper3_format"] and helper5_sha256_full == MODEL_ADAPTER_HELPERS["helper5_tool_call"]):
        return MergeToGgufPlanVerdict("merge_to_gguf", False, "PARTIAL", FAIL_PARTIAL_MERGE_SOURCE_MISSING, input_digest, None, None, None, False)

    if not isinstance(quant_config, dict) or str(quant_config.get("quantization", "")).lower() != "q4_k_m":
        return MergeToGgufPlanVerdict("merge_to_gguf", False, "BLOCKED", FAIL_BLOCK_QUANT_CONFIG_MISMATCH, input_digest, None, None, stable_json_digest(quant_config or {}), False)

    if not is_bare_sha256(output_sha256_full) or not isinstance(size_bytes, int) or size_bytes <= 0:
        return MergeToGgufPlanVerdict("merge_to_gguf", False, "BLOCKED", FAIL_BLOCK_INPUT_SHA_MISMATCH, input_digest, None, size_bytes, stable_json_digest(quant_config), False)

    general_pc = (
        size_bytes <= GENERAL_PC_LIMITS["max_model_size_bytes"]
        and (peak_rss_mb is None or peak_rss_mb <= GENERAL_PC_LIMITS["max_peak_rss_mb"])
        and (latency_ms is None or latency_ms <= GENERAL_PC_LIMITS["max_latency_ms"])
    )
    if not general_pc:
        return MergeToGgufPlanVerdict(
            "merge_to_gguf", True, "BLOCKED", FAIL_BLOCK_GENERAL_PC_BUDGET_EXCEEDED,
            input_digest, "sha256:" + output_sha256_full, size_bytes, stable_json_digest(quant_config), False
        )

    return MergeToGgufPlanVerdict(
        "merge_to_gguf", True, "FUSION_PRODUCED", None,
        input_digest, "sha256:" + output_sha256_full, size_bytes, stable_json_digest(quant_config), True
    )
