from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .constants import (
    SCHEMA_VERSION_MANIFEST,
    MODEL_ADAPTER_HELPERS,
    ALLOWED_FUSION_METHODS,
    ALLOWED_SHA_SCOPE,
    FAIL_BLOCK_MANIFEST_INVALID,
)
from .security import assert_no_raw_or_path_material, assert_ref_or_digest, is_bare_sha256, stable_json_digest


@dataclass(frozen=True)
class FusionModelRef:
    model_choice: str
    sha256_full: str | None
    model_path_ref: str
    readonly_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FusionAdapterRef:
    asset_name: Literal["helper3_format", "helper5_tool_call"]
    role: Literal["format", "intent"]
    sha256_full: str
    sha_scope: Literal["file", "directory_manifest"]
    adapter_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FusionOutputModelRef:
    sha256_full: str
    size_bytes: int
    lightweight_setting: str
    quant_config_digest: str
    output_ref: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoraFusionManifest:
    schema_version: str
    diagnosis_status: Literal["NOT_FUSED_CONFIRMED", "ALREADY_FUSED_CONFIRMED", "INCONCLUSIVE"]
    base_model: FusionModelRef
    adapters: list[FusionAdapterRef]
    fusion_method: Literal["runtime_lora", "merge_to_gguf", "already_fused", "inconclusive"]
    output_model: FusionOutputModelRef | None = None
    raw_saved_zero: bool = True
    external_send_zero: bool = True
    manifest_digest: str | None = None
    notes_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["manifest_digest"] is None:
            core = {k: v for k, v in payload.items() if k != "manifest_digest"}
            payload["manifest_digest"] = stable_json_digest(core)
        assert_no_raw_or_path_material(payload)
        return payload


def build_diagnosis_only_manifest(
    *,
    diagnosis_status: Literal["ALREADY_FUSED_CONFIRMED", "INCONCLUSIVE"],
    base_model_sha256_full: str | None = None,
    base_model_choice: str = "butler-1.7b-v4-rt-q4_k_m.gguf",
) -> LoraFusionManifest:
    method = "already_fused" if diagnosis_status == "ALREADY_FUSED_CONFIRMED" else "inconclusive"
    mapped_status = "ALREADY_FUSED_CONFIRMED" if diagnosis_status == "ALREADY_FUSED_CONFIRMED" else "INCONCLUSIVE"
    adapters = [
        FusionAdapterRef("helper3_format", "format", MODEL_ADAPTER_HELPERS["helper3_format"], "file", "ref:BUTLER_HELPER3_FORMAT_LORA"),
        FusionAdapterRef("helper5_tool_call", "intent", MODEL_ADAPTER_HELPERS["helper5_tool_call"], "file", "ref:BUTLER_HELPER5_TOOL_CALL_LORA"),
    ]
    return LoraFusionManifest(
        schema_version=SCHEMA_VERSION_MANIFEST,
        diagnosis_status=mapped_status,  # type: ignore[arg-type]
        base_model=FusionModelRef(base_model_choice, base_model_sha256_full, "ref:BUTLER_BOX3_BASE_MODEL_PATH", True),
        adapters=adapters,
        fusion_method=method,  # type: ignore[arg-type]
    )


def validate_lora_fusion_manifest(manifest: LoraFusionManifest | dict[str, Any]) -> list[str]:
    payload = manifest.to_dict() if isinstance(manifest, LoraFusionManifest) else dict(manifest)
    errors: list[str] = []
    try:
        assert_no_raw_or_path_material(payload)
    except ValueError:
        errors.append("RAW_OR_PATH_MATERIAL_FORBIDDEN")
    if payload.get("schema_version") != SCHEMA_VERSION_MANIFEST:
        errors.append("SCHEMA_VERSION_INVALID")
    if payload.get("fusion_method") not in ALLOWED_FUSION_METHODS:
        errors.append("FUSION_METHOD_INVALID")
    if payload.get("raw_saved_zero") is not True or payload.get("external_send_zero") is not True:
        errors.append("RAW_OR_EXTERNAL_FLAG_INVALID")

    base = payload.get("base_model")
    if not isinstance(base, dict):
        errors.append("BASE_MODEL_INVALID")
    else:
        if base.get("sha256_full") is not None and not is_bare_sha256(base.get("sha256_full")):
            errors.append("BASE_MODEL_SHA_INVALID")
        try:
            assert_ref_or_digest(base.get("model_path_ref"))
        except ValueError:
            errors.append("BASE_MODEL_PATH_REF_INVALID")

    adapters = payload.get("adapters")
    if not isinstance(adapters, list) or len(adapters) != 2:
        errors.append("ADAPTERS_INVALID")
    else:
        names = {row.get("asset_name") for row in adapters if isinstance(row, dict)}
        if names != set(MODEL_ADAPTER_HELPERS):
            errors.append("ADAPTER_SET_INVALID")
        for row in adapters:
            if not isinstance(row, dict):
                errors.append("ADAPTER_ROW_INVALID")
                continue
            expected = MODEL_ADAPTER_HELPERS.get(row.get("asset_name"))
            if expected is None or row.get("sha256_full") != expected:
                errors.append("ADAPTER_SHA_INVALID")
            if row.get("sha_scope") not in ALLOWED_SHA_SCOPE:
                errors.append("ADAPTER_SHA_SCOPE_INVALID")
            try:
                assert_ref_or_digest(row.get("adapter_ref"))
            except ValueError:
                errors.append("ADAPTER_REF_INVALID")

    method = payload.get("fusion_method")
    output = payload.get("output_model")
    if method == "merge_to_gguf":
        if not isinstance(output, dict):
            errors.append("OUTPUT_MODEL_REQUIRED_FOR_MERGE")
        else:
            if not is_bare_sha256(output.get("sha256_full")):
                errors.append("OUTPUT_MODEL_SHA_INVALID")
            if not isinstance(output.get("size_bytes"), int) or output.get("size_bytes") <= 0:
                errors.append("OUTPUT_SIZE_INVALID")
            if not isinstance(output.get("lightweight_setting"), str) or "q4_k_m" not in output.get("lightweight_setting", "").casefold():
                errors.append("OUTPUT_QUANT_CONFIG_INVALID")
            try:
                assert_ref_or_digest(output.get("output_ref"))
            except ValueError:
                errors.append("OUTPUT_REF_INVALID")
    if method in {"runtime_lora", "already_fused", "inconclusive"} and output is not None:
        errors.append("OUTPUT_MODEL_UNEXPECTED_FOR_METHOD")

    return errors


def manifest_or_block(manifest: LoraFusionManifest | dict[str, Any]) -> tuple[bool, str | None]:
    errors = validate_lora_fusion_manifest(manifest)
    return (not errors, None if not errors else FAIL_BLOCK_MANIFEST_INVALID)
