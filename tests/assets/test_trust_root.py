from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from butler_pc_core.assets.context import PlatformAssetContext
from butler_pc_core.assets.contracts import ReleaseProfile
from butler_pc_core.assets.contracts import AssetEntry, AssetManifest
from butler_pc_core.assets.errors import AssetError
from butler_pc_core.assets.generator import stage_assets
from butler_pc_core.assets.manifest import canonical_json_bytes
from butler_pc_core.assets.service import PRODUCTION_REQUIRED_GROUPS, AssetService

pytestmark = pytest.mark.no_sidecar_token


def _stage(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "source"
    resources = tmp_path / "resources"
    source.mkdir()
    (source / "model.gguf").write_bytes(b"trusted-package-bytes")
    inventory = {
        "schema_version": 1,
        "groups": [
            {
                "asset_group": "free_chat.model",
                "group_version": 1,
                "required_for_profiles": ["test"],
                "entries": [
                    {
                        "role": "model_gguf",
                        "relative_path": "model.gguf",
                        "media_type": "application/octet-stream",
                        "validator": "opaque",
                    }
                ],
            }
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(canonical_json_bytes(inventory))
    digest = stage_assets(
        source_root=source,
        inventory_path=inventory_path,
        resources_root=resources,
        source_commit="1" * 40,
        source_tree="2" * 40,
        release_profile="test",
    )
    return resources, resources / "assets/data/free_chat.model/model.gguf", digest


def test_attacker_policy_and_key_substitution_is_blocked(tmp_path: Path) -> None:
    resources = tmp_path / "package"
    resources.mkdir()
    (resources / "attacker-public-key.json").write_text(
        json.dumps({"key_id": "attacker", "public_key_b64": "AA=="}),
        encoding="utf-8",
    )
    (resources / "attacker-policy.json").write_text(
        json.dumps({"trusted_key": "attacker-public-key.json"}),
        encoding="utf-8",
    )
    context = PlatformAssetContext(
        resource_root=resources,
        app_data_root=tmp_path,
        release_profile=ReleaseProfile.PRODUCTION,
        build_id="1" * 40,
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256="a" * 64,
        native_authority=True,
        trust_root_status="TRUST_ROOT_NOT_CONFIGURED",
    )
    service = AssetService(context)
    service._loaded = True
    fixture_entry = AssetEntry(
        role="fixture",
        relative_path="fixture.bin",
        size_bytes=1,
        sha256="b" * 64,
        media_type="application/octet-stream",
        validator="opaque",
    )
    service._manifests = {
        group: AssetManifest(
            asset_group=group,
            group_version=1,
            required_for_profiles=("production",),
            entries=(fixture_entry,),
            digest="c" * 64,
        )
        for group in PRODUCTION_REQUIRED_GROUPS
    }
    with pytest.raises(AssetError, match="BLOCK_TRUST_UNAVAILABLE"):
        service.enforce_profile_contract("production")


def test_package_byte_mutation_is_blocked(tmp_path: Path) -> None:
    resources, model, manifest_set = _stage(tmp_path)
    model.chmod(0o600)
    model.write_bytes(b"attacker-package-bytes")
    context = PlatformAssetContext(
        resource_root=resources,
        app_data_root=tmp_path,
        release_profile=ReleaseProfile.TEST,
        build_id="test-build",
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256=manifest_set,
        native_authority=True,
    )
    with pytest.raises(AssetError, match="FILE_(?:SIZE|DIGEST)_MISMATCH"):
        AssetService(context).acquire(
            role="free_chat.model",
            purpose="mutation-probe",
            expected_manifest_set=manifest_set,
            request_id=str(uuid.uuid4()),
        )
