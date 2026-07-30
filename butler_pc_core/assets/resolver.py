from __future__ import annotations

from dataclasses import dataclass

from .contracts import AssetEntry, AssetManifest
from .errors import block


@dataclass(frozen=True)
class ResolvedCapability:
    capability: str
    manifest: AssetManifest
    entries: tuple[AssetEntry, ...]


class AssetResolver:
    """Resolve logical capabilities without exposing or opening filesystem paths."""

    def __init__(
        self,
        manifests: dict[str, AssetManifest],
        capability_groups: dict[str, tuple[str, tuple[str, ...]]],
    ) -> None:
        self._manifests = dict(manifests)
        self._capability_groups = dict(capability_groups)

    def resolve(self, capability: str) -> ResolvedCapability:
        try:
            group, required_roles = self._capability_groups[capability]
        except KeyError as exc:
            raise block("CAPABILITY_UNKNOWN") from exc
        manifest = self._manifests.get(group)
        if manifest is None:
            raise block("REQUIRED_ASSET_MISSING")
        by_role = {entry.role: entry for entry in manifest.entries}
        if not set(required_roles) <= set(by_role):
            raise block("REQUIRED_ASSET_MISSING")
        self._enforce_model_identity(capability, by_role)
        return ResolvedCapability(
            capability=capability,
            manifest=manifest,
            entries=tuple(by_role[role] for role in sorted(by_role)),
        )

    @staticmethod
    def _enforce_model_identity(
        capability: str, by_role: dict[str, AssetEntry]
    ) -> None:
        if capability == "box2.adapter":
            base = by_role["base_model"]
            for role in ("butler_adapter", "rewrite_adapter"):
                identity = by_role[role].model_identity
                if (
                    identity is None
                    or identity.get("base_model_sha256") != base.sha256
                ):
                    raise block("ADAPTER_BASE_MISMATCH")
        elif capability == "accounting.adapter":
            base = by_role["base_model_weights"]
            identity = by_role["adapter_weights"].model_identity
            if (
                identity is None
                or identity.get("base_model_sha256") != base.sha256
            ):
                raise block("ADAPTER_BASE_MISMATCH")
        elif capability in {
            "helper1.ask",
            "ip3.model",
            "semantic_mapping.model",
        }:
            model_role = {
                "helper1.ask": "ask_model_gguf",
                "ip3.model": "model_gguf",
                "semantic_mapping.model": "model_gguf",
            }[capability]
            if by_role[model_role].model_identity is None:
                raise block("MODEL_IDENTITY_MISMATCH")
