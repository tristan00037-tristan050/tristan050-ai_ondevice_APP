from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path

from .context import PlatformAssetContext, get_platform_context
from .contracts import (
    AssetManifest,
    CapabilityLease,
    GroupState,
    GroupStatus,
    VerificationReceipt,
)
from .errors import AssetError, block
from .manifest import manifest_set_root, parse_manifest
from .receipts import issue_group_receipt
from .resolver import AssetResolver
from .verifier import SafeRoot, verify_entry

VERIFIER_VERSION = "butler.assets.v2"
MANIFEST_DIRECTORY = "assets/manifests"
ASSET_DATA_DIRECTORY = "assets/data"
MAX_MANIFEST_FILES = 128

CAPABILITY_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "helper1.search": (
        "helper1.search",
        ("chunks_jsonl", "embeddings_npy"),
    ),
    "helper1.ask": (
        "helper1.ask",
        ("ask_model_gguf",),
    ),
    "ip3.model": (
        "ip3.model",
        ("model_gguf",),
    ),
    "box2.adapter": (
        "box2.adapter",
        ("base_model", "butler_adapter", "rewrite_adapter"),
    ),
    "accounting.adapter": (
        "accounting.adapter",
        (
            "adapter_config",
            "adapter_weights",
            "base_model_config",
            "base_model_weights",
            "tokenizer_config",
        ),
    ),
    "semantic_mapping.model": (
        "semantic_mapping.model",
        ("model_gguf",),
    ),
    "box3.helpers": (
        "box3.helpers",
        (
            "helper3_format",
            "helper4_grounding",
            "helper7_table_figure",
            "helper8_company_style",
        ),
    ),
}
PRODUCTION_REQUIRED_GROUPS = frozenset(
    group for group, _roles in CAPABILITY_GROUPS.values()
)


class AssetService:
    def __init__(self, context: PlatformAssetContext | None = None) -> None:
        self._context = context or get_platform_context()
        self._lock = threading.RLock()
        self._manifests: dict[str, AssetManifest] = {}
        self._statuses: dict[str, GroupStatus] = {}
        self._receipts: dict[str, VerificationReceipt] = {}
        self._failures: dict[str, AssetError] = {}
        self._inflight: set[str] = set()
        self._condition = threading.Condition(self._lock)
        self._run_id = secrets.token_hex(16)
        self._loaded = False

    def _load_manifests(self) -> None:
        with self._lock:
            if self._loaded:
                return
            manifest_root = self._context.resource_root / MANIFEST_DIRECTORY
            if not manifest_root.exists():
                self._loaded = True
                return
            with SafeRoot(manifest_root) as safe_root:
                names = sorted(
                    item.name
                    for item in manifest_root.iterdir()
                    if item.name.endswith(".manifest.json")
                )
                if len(names) > MAX_MANIFEST_FILES:
                    raise block("RESOURCE_LIMIT_EXCEEDED")
                manifests: dict[str, AssetManifest] = {}
                for name in names:
                    fd = safe_root.open_regular(name)
                    try:
                        with os.fdopen(fd, "rb", closefd=True) as handle:
                            raw = handle.read(4 * 1024 * 1024 + 1)
                    except Exception:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                        raise
                    manifest = parse_manifest(raw)
                    if manifest.asset_group in manifests:
                        raise block("MANIFEST_SCHEMA_INVALID")
                    manifests[manifest.asset_group] = manifest
            actual_set = manifest_set_root(manifests.values())
            expected_set = self._context.manifest_set_sha256
            if expected_set is None:
                if self._context.release_profile.value == "production" and manifests:
                    raise block("MANIFEST_BUILD_BINDING_MISMATCH")
            elif not secrets.compare_digest(actual_set, expected_set):
                raise block("MANIFEST_BUILD_BINDING_MISMATCH")
            self._manifests = manifests
            for group, manifest in manifests.items():
                self._statuses.setdefault(
                    group,
                    GroupStatus(
                        group,
                        manifest.group_version,
                        GroupState.VERIFYING,
                        "VERIFYING",
                    ),
                )
            self._loaded = True

    def verify_required_groups(self, profile: str | None = None) -> tuple[VerificationReceipt, ...]:
        self._load_manifests()
        selected = profile or self._context.release_profile.value
        self.enforce_profile_contract(selected)
        receipts: list[VerificationReceipt] = []
        for manifest in self._manifests.values():
            if selected in manifest.required_for_profiles:
                receipts.append(self._verify_group(manifest))
            else:
                self._statuses[manifest.asset_group] = GroupStatus(
                    manifest.asset_group,
                    manifest.group_version,
                    GroupState.NOT_REQUIRED,
                    "NOT_REQUIRED",
                )
        return tuple(receipts)

    def verify_all_groups(self) -> tuple[VerificationReceipt, ...]:
        self._load_manifests()
        return tuple(
            self._verify_group(manifest)
            for manifest in sorted(
                self._manifests.values(), key=lambda item: item.asset_group
            )
        )

    def enforce_profile_contract(self, profile: str) -> None:
        self._load_manifests()
        if profile != "production":
            return
        missing = PRODUCTION_REQUIRED_GROUPS - set(self._manifests)
        if missing:
            raise block("REQUIRED_ASSET_MISSING")
        if any(
            "production" not in self._manifests[group].required_for_profiles
            for group in PRODUCTION_REQUIRED_GROUPS
        ):
            raise block("REQUIRED_ASSET_MISSING")

    def _verify_group(self, manifest: AssetManifest) -> VerificationReceipt:
        group = manifest.asset_group
        with self._condition:
            cached = self._receipts.get(group)
            if cached is not None:
                return cached
            failure = self._failures.get(group)
            if failure is not None:
                raise failure
            while group in self._inflight:
                self._condition.wait()
                cached = self._receipts.get(group)
                if cached is not None:
                    return cached
                failure = self._failures.get(group)
                if failure is not None:
                    raise failure
            self._inflight.add(group)
            self._statuses[manifest.asset_group] = GroupStatus(
                manifest.asset_group,
                manifest.group_version,
                GroupState.VERIFYING,
                None,
            )
        data_root = self._context.resource_root / ASSET_DATA_DIRECTORY / manifest.asset_group
        assets = {}
        try:
            with SafeRoot(data_root) as root:
                for entry in manifest.entries:
                    assets[entry.role] = verify_entry(root, entry)
            receipt = issue_group_receipt(
                run_id=self._run_id,
                build_id=self._context.build_id,
                release_profile=self._context.release_profile.value,
                manifest_set_sha256=self._context.manifest_set_sha256,
                manifest=manifest,
                assets=assets,
                verifier_version=VERIFIER_VERSION,
            )
        except Exception as raw_exc:
            exc = (
                raw_exc
                if isinstance(raw_exc, AssetError)
                else block("VERIFY_IO_ERROR")
            )
            for asset in assets.values():
                asset.close()
            with self._condition:
                self._failures[group] = exc
                self._inflight.discard(group)
                self._statuses[manifest.asset_group] = GroupStatus(
                    manifest.asset_group,
                    manifest.group_version,
                    GroupState.UNAVAILABLE,
                    exc.code,
                )
                self._condition.notify_all()
            if exc is raw_exc:
                raise
            raise exc from raw_exc
        for asset in assets.values():
            asset.close()
        with self._condition:
            self._receipts[manifest.asset_group] = receipt
            self._inflight.discard(group)
            self._statuses[manifest.asset_group] = GroupStatus(
                manifest.asset_group,
                manifest.group_version,
                GroupState.AVAILABLE,
                None,
            )
            self._condition.notify_all()
        return receipt

    def require_capability(self, capability: str) -> CapabilityLease:
        self._load_manifests()
        try:
            resolved = AssetResolver(
                self._manifests, CAPABILITY_GROUPS
            ).resolve(capability)
        except AssetError as exc:
            if exc.code != "REQUIRED_ASSET_MISSING":
                raise
            group = CAPABILITY_GROUPS.get(capability, (capability, ()))[0]
            self._statuses[group] = GroupStatus(
                group, 1, GroupState.NOT_INSTALLED, "NOT_INSTALLED"
            )
            raise
        group = resolved.manifest.asset_group
        manifest = resolved.manifest

        data_root = self._context.resource_root / ASSET_DATA_DIRECTORY / group
        assets = {}
        try:
            with SafeRoot(data_root) as root:
                for entry in resolved.entries:
                    assets[entry.role] = verify_entry(root, entry)
            return CapabilityLease(
                capability=capability,
                asset_group=group,
                group_version=manifest.group_version,
                assets=assets,
            )
        except Exception as raw_exc:
            for asset in assets.values():
                asset.close()
            if isinstance(raw_exc, AssetError):
                raise
            raise block("VERIFY_IO_ERROR") from raw_exc

    def get_cached_status(self) -> dict[str, object]:
        self._load_manifests()
        statuses = dict(self._statuses)
        for group, manifest in self._manifests.items():
            statuses.setdefault(
                group,
                GroupStatus(
                    group,
                    manifest.group_version,
                    GroupState.VERIFYING,
                    "VERIFYING",
                ),
            )
        values = sorted(statuses.values(), key=lambda item: item.asset_group)
        if not values:
            overall = (
                "UNAVAILABLE"
                if self._context.release_profile.value == "production"
                else "DEGRADED"
            )
        elif any(item.state is GroupState.UNAVAILABLE for item in values):
            overall = "UNAVAILABLE"
        elif any(item.state is GroupState.VERIFYING for item in values):
            overall = "VERIFYING"
        elif any(item.state is GroupState.NOT_INSTALLED for item in values):
            overall = "DEGRADED"
        else:
            overall = "AVAILABLE"
        groups = []
        for item in values:
            row: dict[str, object] = {
                "asset_group": item.asset_group,
                "group_version": item.group_version,
                "state": item.state.value,
            }
            if item.reason:
                row["reason"] = _external_reason(item.reason)
            groups.append(row)
        return {"schema_version": 1, "overall_state": overall, "groups": groups}


def _external_reason(reason: str) -> str:
    if reason in {"NOT_INSTALLED", "NOT_REQUIRED"}:
        return reason
    if reason == "VERIFYING":
        return reason
    if reason in {
        "FILE_DIGEST_MISMATCH",
        "FILE_SIZE_MISMATCH",
        "FORMAT_SCHEMA_INVALID",
        "UNSAFE_SERIALIZATION",
        "MANIFEST_BUILD_BINDING_MISMATCH",
    }:
        return "ASSET_INVALID"
    return "ASSET_UNAVAILABLE"


_DEFAULT_LOCK = threading.Lock()
_DEFAULT: AssetService | None = None


def get_asset_service() -> AssetService:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = AssetService()
        return _DEFAULT


def reset_asset_service_for_tests() -> None:
    global _DEFAULT
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        raise block("OVERRIDE_FORBIDDEN")
    with _DEFAULT_LOCK:
        _DEFAULT = None
