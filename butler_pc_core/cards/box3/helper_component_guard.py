from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .actual_fail_class import BLOCK_HELPER_REAL_USE_GUARD_PENDING
from .helper_wiring_manifest import (
    HELPER_SHA,
    REQUIRED_MODEL_ADAPTERS,
    REQUIRED_SDK_MODULES,
    build_example_helper_wiring_manifest,
    validate_helper_wiring_manifest,
)

# Backward-compatible expected SHA map. helper5 is now required for model-adapter stack.
HELPER_EXPECTED_SHA = dict(HELPER_SHA)

@dataclass(frozen=True)
class HelperComponentGuardVerdict:
    allowed: bool
    fail_class: str | None
    component_use_allowed_count: int
    helper_count: int
    helper_stack_supported: bool
    sdk_call_supported: bool
    embedder_provider: str | None
    helper_digests: dict[str, str]
    role_detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _from_legacy_guard(guard: dict[str, Any]) -> dict[str, Any] | None:
    """Translate PR #778 helper list shape into HelperWiringManifest v1.2 if possible."""
    helpers = guard.get("helpers")
    if not isinstance(helpers, list):
        return None
    by_name = {row.get("asset_name"): row for row in helpers if isinstance(row, dict)}
    # Legacy guard only had helper3/4/7/8. In v1.2 helper5 is required; do not fabricate it.
    if "helper5_tool_call" not in by_name:
        return None
    return {
        "schema_version": "box3.helper_wiring_manifest.v1.2",
        "model_stack_supported": guard.get("helper_stacking_supported") is True or guard.get("model_stack_supported") is True,
        "sdk_call_allowed": guard.get("sdk_call_supported") is True,
        "raw_saved_zero": True,
        "model_adapters": [
            {
                "asset_name": name,
                "component_type": "model_adapter",
                "sha256_full": by_name.get(name, {}).get("sha256_full"),
                "component_use_allowed": by_name.get(name, {}).get("component_use_allowed") is True,
                "model_stack_supported": guard.get("helper_stacking_supported") is True or guard.get("model_stack_supported") is True,
                "sdk_call_allowed": False,
                "adapter_path_ref": by_name.get(name, {}).get("path_ref") or f"ref:BUTLER_{name.upper()}_PATH",
            }
            for name in REQUIRED_MODEL_ADAPTERS
        ],
        "sdk_modules": [
            {
                "asset_name": name,
                "component_type": "sdk_module",
                "sha256_full": by_name.get(name, {}).get("sha256_full"),
                "component_use_allowed": by_name.get(name, {}).get("component_use_allowed") is True,
                "model_stack_supported": False,
                "sdk_call_allowed": guard.get("sdk_call_supported") is True,
                "requires": ["helper2_embedding"] if name == "helper4_grounding" else [],
                "sdk_module_ref": by_name.get(name, {}).get("path_ref") or f"ref:BUTLER_{name.upper()}_SDK",
            }
            for name in REQUIRED_SDK_MODULES
        ],
        "embedding_dependencies": [
            {
                "asset_name": "helper2_embedding",
                "provider": guard.get("embedder_provider") or "missing",
                "component_type": "embedding_dependency",
                "component_use_allowed": bool(guard.get("embedder_provider")),
                "sdk_call_allowed": bool(guard.get("embedder_provider")),
            }
        ],
    }

def verify_helper_component_use_guard(guard: dict[str, Any] | None) -> HelperComponentGuardVerdict:
    manifest = guard
    if isinstance(guard, dict) and guard.get("schema_version") != "box3.helper_wiring_manifest.v1.2":
        manifest = _from_legacy_guard(guard)
    verdict = validate_helper_wiring_manifest(manifest if isinstance(manifest, dict) else None)
    if not verdict.allowed:
        return HelperComponentGuardVerdict(
            False,
            verdict.fail_class or BLOCK_HELPER_REAL_USE_GUARD_PENDING,
            0,
            0,
            False,
            False,
            None,
            {},
            verdict.detail,
        )

    detail = verdict.detail
    model_adapters = detail.get("model_adapters", {})
    sdk_modules = detail.get("sdk_modules", {})
    embeddings = detail.get("embedding_dependencies", {})
    digests: dict[str, str] = {}
    for name, row in {**model_adapters, **sdk_modules}.items():
        if isinstance(row, dict) and isinstance(row.get("sha256_full"), str):
            digests[name] = row["sha256_full"]
    provider = None
    if isinstance(embeddings.get("helper2_embedding"), dict):
        provider = embeddings["helper2_embedding"].get("provider")
    return HelperComponentGuardVerdict(
        True,
        None,
        len(model_adapters) + len(sdk_modules),
        len(model_adapters) + len(sdk_modules),
        True,
        True,
        provider,
        digests,
        detail,
    )

def build_example_component_use_guard(
    *,
    allow: bool = False,
    stack_supported: bool = False,
    sdk_call_supported: bool = False,
    embedder_provider: str | None = None,
) -> dict[str, Any]:
    return build_example_helper_wiring_manifest(
        component_use_allowed=allow,
        adapter_stack_supported=stack_supported,
        sdk_call_supported=sdk_call_supported,
        embedder_provider=embedder_provider,
    )
