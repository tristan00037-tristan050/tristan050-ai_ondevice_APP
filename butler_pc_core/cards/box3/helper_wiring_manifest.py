from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .actual_contracts import stable_json_digest
from .actual_fail_class import (
    BLOCK_HELPER8_NON_CANONICAL_SHA,
    BLOCK_HELPER_ASSET_DRIFT,
    BLOCK_HELPER_REAL_USE_GUARD_PENDING,
    BLOCK_HELPER_SDK_STACK_ATTEMPT,
    PARTIAL_EMBEDDER_UNAVAILABLE,
    PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED,
)

SCHEMA_VERSION = "box3.helper_wiring_manifest.v1.2"
_SHA_RE = re.compile(r"^[a-f0-9]{64}$")

HELPER_SHA = {
    "helper3_format": "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0",
    "helper5_tool_call": "ad852bbb79aee63cc68750eac3ebe02de372d4eb9529659ae065490c78c933ca",
    "helper4_grounding": "b7b1af0ebfddc17bf9164ab124f8b598d97954f1a9fa067abf1e68f020c95e40",
    "helper7_table_figure": "8b03454967a9f16d12e408ea85ab3b27efe5a3e053c8150480cb70646fa4dfb0",
    "helper8_company_style": "7d4f8311ab427e4b609e2d22d7aff6e89a19085eaaa788677c7ed24d789d6d52",
}
REQUIRED_MODEL_ADAPTERS = ("helper3_format", "helper5_tool_call")
REQUIRED_SDK_MODULES = ("helper4_grounding", "helper7_table_figure", "helper8_company_style")
NON_CANONICAL_HELPER8_PREFIX = "be18" + "e3cc"

@dataclass(frozen=True)
class HelperRoleVerdict:
    allowed: bool
    fail_class: str | None
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _is_sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))

def _rows_by_name(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    out = {}
    for item in rows:
        if isinstance(item, dict) and isinstance(item.get("asset_name"), str):
            out[item["asset_name"]] = item
    return out

def build_example_helper_wiring_manifest(
    *,
    component_use_allowed: bool = False,
    adapter_stack_supported: bool = False,
    sdk_call_supported: bool = False,
    embedder_provider: str | None = None,
) -> dict[str, Any]:
    """Digest-only example. It contains no local path and can be used in tests/evidence."""
    return {
        "schema_version": SCHEMA_VERSION,
        "model_stack_supported": bool(adapter_stack_supported),
        "sdk_call_allowed": bool(sdk_call_supported),
        "raw_saved_zero": True,
        "model_adapters": [
            {
                "asset_name": name,
                "component_type": "model_adapter",
                "sha256_full": HELPER_SHA[name],
                "component_use_allowed": bool(component_use_allowed),
                "model_stack_supported": bool(adapter_stack_supported),
                "sdk_call_allowed": False,
                "adapter_path_ref": f"ref:BUTLER_{name.upper()}_PATH",
                "fail_class": None,
            }
            for name in REQUIRED_MODEL_ADAPTERS
        ],
        "sdk_modules": [
            {
                "asset_name": name,
                "component_type": "sdk_module",
                "sha256_full": HELPER_SHA[name],
                "component_use_allowed": bool(component_use_allowed),
                "model_stack_supported": False,
                "sdk_call_allowed": bool(sdk_call_supported),
                "sdk_module_ref": f"ref:BUTLER_{name.upper()}_SDK",
                "requires": ["helper2_embedding"] if name == "helper4_grounding" else [],
                "fail_class": None,
            }
            for name in REQUIRED_SDK_MODULES
        ],
        "embedding_dependencies": [
            {
                "asset_name": "helper2_embedding",
                "provider": embedder_provider or "missing",
                "component_type": "embedding_dependency",
                "component_use_allowed": bool(component_use_allowed and embedder_provider),
                "sdk_call_allowed": bool(embedder_provider),
                "fail_class": None if embedder_provider else PARTIAL_EMBEDDER_UNAVAILABLE,
            }
        ],
    }

def validate_helper_wiring_manifest(manifest: dict[str, Any] | None) -> HelperRoleVerdict:
    if not isinstance(manifest, dict):
        return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"reason": "manifest_missing"})
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"reason": "schema_version"})
    adapters = _rows_by_name(manifest.get("model_adapters"))
    sdk_modules = _rows_by_name(manifest.get("sdk_modules"))
    embeddings = _rows_by_name(manifest.get("embedding_dependencies"))
    if set(adapters) != set(REQUIRED_MODEL_ADAPTERS):
        return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"missing_model_adapters": sorted(set(REQUIRED_MODEL_ADAPTERS) - set(adapters))})
    if set(sdk_modules) != set(REQUIRED_SDK_MODULES):
        return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"missing_sdk_modules": sorted(set(REQUIRED_SDK_MODULES) - set(sdk_modules))})

    detail: dict[str, Any] = {
        "manifest_digest": stable_json_digest(manifest),
        "model_adapters": {},
        "sdk_modules": {},
        "embedding_dependencies": {},
    }

    for name in REQUIRED_MODEL_ADAPTERS:
        row = adapters[name]
        expected = HELPER_SHA[name]
        if row.get("sha256_full") != expected or not _is_sha(row.get("sha256_full")):
            return HelperRoleVerdict(False, BLOCK_HELPER_ASSET_DRIFT, {"asset_name": name})
        if row.get("component_use_allowed") is not True:
            return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"asset_name": name})
        if row.get("model_stack_supported") is not True or manifest.get("model_stack_supported") is not True:
            return HelperRoleVerdict(False, PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED, {"asset_name": name})
        if row.get("sdk_call_allowed") is True:
            return HelperRoleVerdict(False, BLOCK_HELPER_SDK_STACK_ATTEMPT, {"asset_name": name, "reason": "model_adapter_marked_sdk"})
        detail["model_adapters"][name] = {"sha256_full": expected, "model_stack_supported": True}

    for name in REQUIRED_SDK_MODULES:
        row = sdk_modules[name]
        expected = HELPER_SHA[name]
        digest = row.get("sha256_full")
        if name == "helper8_company_style" and isinstance(digest, str) and digest.startswith(NON_CANONICAL_HELPER8_PREFIX):
            return HelperRoleVerdict(False, BLOCK_HELPER8_NON_CANONICAL_SHA, {"asset_name": name})
        if digest != expected or not _is_sha(digest):
            return HelperRoleVerdict(False, BLOCK_HELPER_ASSET_DRIFT, {"asset_name": name})
        if row.get("component_use_allowed") is not True:
            return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"asset_name": name})
        if row.get("model_stack_supported") is True or row.get("stack_requested") is True:
            return HelperRoleVerdict(False, BLOCK_HELPER_SDK_STACK_ATTEMPT, {"asset_name": name})
        if row.get("sdk_call_allowed") is not True or manifest.get("sdk_call_allowed") is not True:
            return HelperRoleVerdict(False, BLOCK_HELPER_REAL_USE_GUARD_PENDING, {"asset_name": name, "reason": "sdk_call_not_allowed"})
        detail["sdk_modules"][name] = {"sha256_full": expected, "sdk_call_allowed": True}

    embedder = embeddings.get("helper2_embedding")
    if not isinstance(embedder, dict) or embedder.get("sdk_call_allowed") is not True:
        return HelperRoleVerdict(False, PARTIAL_EMBEDDER_UNAVAILABLE, {"asset_name": "helper2_embedding"})
    provider = embedder.get("provider")
    if provider not in {"helper2_sdk", "bge_m3"}:
        return HelperRoleVerdict(False, PARTIAL_EMBEDDER_UNAVAILABLE, {"asset_name": "helper2_embedding", "provider": provider})
    detail["embedding_dependencies"]["helper2_embedding"] = {"provider": provider}

    return HelperRoleVerdict(True, None, detail)
