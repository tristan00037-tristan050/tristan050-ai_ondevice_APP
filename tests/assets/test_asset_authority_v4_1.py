from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import struct
import threading
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import butler_pc_core.assets.verifier as asset_verifier
from butler_pc_core.assets.atomic_publish import atomic_publish_noreplace
from butler_pc_core.assets.context import PlatformAssetContext
from butler_pc_core.assets.contracts import (
    AssetEntry,
    AssetManifest,
    LeaseState,
    ReleaseProfile,
)
from butler_pc_core.assets.errors import AssetError
from butler_pc_core.assets.formats import validate_format
from butler_pc_core.assets.generator import stage_assets
from butler_pc_core.assets.manifest import canonical_json_bytes
from butler_pc_core.assets.provenance import (
    GitOID,
    VerifiedProvenance,
    verify_signed_provenance,
)
from butler_pc_core.assets.service import (
    PRODUCTION_REQUIRED_GROUPS,
    AssetService,
)

pytestmark = pytest.mark.no_sidecar_token


def _stage_opaque(tmp_path: Path) -> tuple[Path, Path, str, bytes]:
    payload = b"immutable-product-asset"
    source = tmp_path / "source"
    resources = tmp_path / "resources"
    source.mkdir()
    (source / "model.bin").write_bytes(payload)
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
                        "relative_path": "model.bin",
                        "media_type": "application/octet-stream",
                        "validator": "opaque",
                    }
                ],
            }
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(canonical_json_bytes(inventory))
    manifest_set = stage_assets(
        source_root=source,
        inventory_path=inventory_path,
        resources_root=resources,
        source_commit="1" * 40,
        source_tree="2" * 40,
        release_profile="test",
    )
    return resources, resources / "assets/data/free_chat.model/model.bin", manifest_set, payload


def _context(resources: Path, manifest_set: str) -> PlatformAssetContext:
    return PlatformAssetContext(
        resource_root=resources,
        app_data_root=resources,
        release_profile=ReleaseProfile.TEST,
        build_id="build-v4-1",
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256=manifest_set,
        native_authority=True,
    )


def _entry(raw: bytes, validator: str, suffix: str) -> AssetEntry:
    return AssetEntry(
        role="fixture",
        relative_path=f"fixture.{suffix}",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type="application/octet-stream",
        validator=validator,
    )


def test_same_inode_source_mutation_cannot_change_active_lease(tmp_path: Path) -> None:
    resources, source, manifest_set, original = _stage_opaque(tmp_path)
    service = AssetService(_context(resources, manifest_set))
    lease = service.acquire(
        role="free_chat.model",
        purpose="mutation-attack",
        expected_manifest_set=manifest_set,
        request_id=str(uuid.uuid4()),
    )
    try:
        before_inode = source.stat().st_ino
        source.chmod(0o600)
        with source.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"X" * len(original))
            handle.flush()
            os.fsync(handle.fileno())
        assert source.stat().st_ino == before_inode
        with lease.require("model_gguf").open() as sealed:
            leased = sealed.read()
        receipt = lease.receipt("model_gguf")
        assert leased == original
        assert hashlib.sha256(leased).hexdigest() == receipt.loader_input_digest
        assert receipt.asset_digest == receipt.snapshot_digest == receipt.loader_input_digest
    finally:
        lease.close()
    assert lease.state is LeaseState.LEASE_CLOSED
    with pytest.raises(RuntimeError, match="LEASE_NOT_ACTIVE"):
        lease.require("model_gguf")


def test_source_change_after_snapshot_blocks_and_closes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources, source, _manifest_set, original = _stage_opaque(tmp_path)
    entry = asset_verifier.AssetEntry(
        role="model_gguf",
        relative_path="model.bin",
        size_bytes=len(original),
        sha256=hashlib.sha256(original).hexdigest(),
        media_type="application/octet-stream",
        validator="opaque",
    )
    real_snapshot = asset_verifier.create_sealed_snapshot
    captured_fd = -1

    def snapshot_then_mutate(
        source_fd: int, *, expected_size: int, authority_root: Path | None
    ):
        nonlocal captured_fd
        snapshot = real_snapshot(
            source_fd,
            expected_size=expected_size,
            authority_root=authority_root,
        )
        captured_fd = snapshot.fd
        source.chmod(0o600)
        source.write_bytes(b"X" * len(original))
        return snapshot

    monkeypatch.setattr(
        asset_verifier, "create_sealed_snapshot", snapshot_then_mutate
    )
    with asset_verifier.SafeRoot(
        source.parent, authority_root=resources
    ) as root:
        with pytest.raises(AssetError, match="TOCTOU_CHANGED"):
            asset_verifier.verify_entry(root, entry)
    assert captured_fd >= 0
    with pytest.raises(OSError):
        os.fstat(captured_fd)


def test_production_source_oid_must_match_native_build_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = PlatformAssetContext(
        resource_root=tmp_path,
        app_data_root=tmp_path,
        release_profile=ReleaseProfile.PRODUCTION,
        build_id="1" * 40,
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256="a" * 64,
        native_authority=True,
    )
    entry = _entry(b"x", "opaque", "bin")
    service = AssetService(context)
    service._loaded = True
    service._manifests = {
        group: AssetManifest(
            asset_group=group,
            group_version=1,
            required_for_profiles=("production",),
            entries=(entry,),
            digest="b" * 64,
        )
        for group in PRODUCTION_REQUIRED_GROUPS
    }
    monkeypatch.setattr(
        "butler_pc_core.assets.service.verify_packaged_provenance",
        lambda *_args, **_kwargs: VerifiedProvenance(
            source_oid=GitOID("sha1", "3" * 40),
            source_tree_oid=GitOID("sha1", "2" * 40),
            pr_head_oid=GitOID("sha1", "3" * 40),
            manifest_set_sha256="a" * 64,
            package_sha256="c" * 64,
            trust_policy_digest="d" * 64,
            signer_key_id="release-key",
            builder_id="trusted-builder",
            workflow_id="trusted-workflow",
        ),
    )
    with pytest.raises(AssetError, match="BLOCK_SOURCE_BINDING_MISMATCH"):
        service.enforce_profile_contract("production")


def test_safetensors_67_byte_declared_end_1003_is_blocked() -> None:
    header = canonical_json_bytes(
        {"a": {"dtype": "I8", "shape": [], "data_offsets": [0, 1003]}}
    )
    assert len(header) + 8 <= 67
    raw = struct.pack("<Q", len(header)) + header
    raw += b"\0" * (67 - len(raw))
    assert len(raw) == 67
    with pytest.raises(AssetError, match="BLOCK_FORMAT_INVALID"):
        validate_format(io.BytesIO(raw), _entry(raw, "safetensors", "safetensors"))


def test_safetensors_hole_and_shape_overflow_are_blocked() -> None:
    hole_header = canonical_json_bytes(
        {"a": {"dtype": "I8", "shape": [1], "data_offsets": [1, 2]}}
    )
    hole = struct.pack("<Q", len(hole_header)) + hole_header + b"\0\0"
    with pytest.raises(AssetError, match="BLOCK_FORMAT_INVALID"):
        validate_format(io.BytesIO(hole), _entry(hole, "safetensors", "safetensors"))

    overflow_header = canonical_json_bytes(
        {
            "a": {
                "dtype": "F64",
                "shape": [1_000_000_000, 1_000_000_000],
                "data_offsets": [0, 0],
            }
        }
    )
    overflow = struct.pack("<Q", len(overflow_header)) + overflow_header
    with pytest.raises(AssetError, match="INTEGER_OVERFLOW"):
        validate_format(
            io.BytesIO(overflow), _entry(overflow, "safetensors", "safetensors")
        )


def _gguf_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def test_minimal_gguf_closure_and_unknown_type_blocking() -> None:
    valid = b"GGUF" + struct.pack("<IQQ", 3, 0, 0) + b"\0" * 8
    validate_format(io.BytesIO(valid), _entry(valid, "gguf", "gguf"))

    invalid = (
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + _gguf_string("general.alignment")
        + struct.pack("<I", 0xFFFF_FFFF)
    )
    with pytest.raises(AssetError, match="BLOCK_FORMAT_INVALID"):
        validate_format(io.BytesIO(invalid), _entry(invalid, "gguf", "gguf"))


def test_atomic_publish_is_no_clobber_under_race(tmp_path: Path) -> None:
    target = tmp_path / "published"
    sources = []
    for index in range(2):
        source = tmp_path / f"stage-{index}"
        source.mkdir()
        (source / "payload").write_text(str(index), encoding="ascii")
        sources.append(source)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def publish(source: Path) -> None:
        barrier.wait()
        try:
            atomic_publish_noreplace(source, target)
            outcomes.append("published")
        except AssetError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=publish, args=(source,)) for source in sources]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert sorted(outcomes) == ["PUBLISH_TARGET_EXISTS", "published"]
    assert (target / "payload").read_text(encoding="ascii") in {"0", "1"}


def _write_signed_provenance(
    tmp_path: Path, *, tamper: bool = False
) -> tuple[Path, Path, str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    policy = {
        "schema_version": 1,
        "allowed_oid_algorithms": ["sha1"],
        "allowed_repository_uris": ["https://example.invalid/butler.git"],
        "allowed_builder_ids": ["github-actions"],
        "allowed_workflow_ids": ["asset-release-v4"],
        "signing_keys": [
            {
                "key_id": "release-key-1",
                "algorithm": "ed25519",
                "public_key_b64": base64.b64encode(public_key).decode("ascii"),
            }
        ],
    }
    policy_raw = canonical_json_bytes(policy)
    manifest_set = "a" * 64
    package_sha = "b" * 64
    payload = {
        "package_sha256": package_sha,
        "repository_uri": "https://example.invalid/butler.git",
        "source_oid": {"algorithm": "sha1", "hex": "1" * 40},
        "source_tree_oid": {"algorithm": "sha1", "hex": "2" * 40},
        "manifest_set_sha256": manifest_set,
        "build_configuration_sha256": "c" * 64,
        "builder_id": "github-actions",
        "workflow_id": "asset-release-v4",
        "invocation_id": "run-123",
        "pr_head_oid": {"algorithm": "sha1", "hex": "1" * 40},
        "trust_policy_sha256": hashlib.sha256(policy_raw).hexdigest(),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    if tamper:
        payload["builder_id"] = "untrusted-builder"
    envelope = {
        "schema_version": 1,
        "payload": payload,
        "signature": {
            "algorithm": "ed25519",
            "key_id": "release-key-1",
            "value_b64": base64.b64encode(signature).decode("ascii"),
        },
    }
    policy_path = tmp_path / "trust-policy.v1.json"
    provenance_path = tmp_path / "provenance.v1.json"
    policy_path.write_bytes(policy_raw)
    provenance_path.write_bytes(canonical_json_bytes(envelope))
    return policy_path, provenance_path, manifest_set, package_sha


def test_signed_provenance_is_externally_pinned_and_tamper_evident(
    tmp_path: Path,
) -> None:
    policy, provenance, manifest_set, package_sha = _write_signed_provenance(
        tmp_path
    )
    verified = verify_signed_provenance(
        trust_policy_path=policy,
        provenance_path=provenance,
        expected_manifest_set=manifest_set,
        expected_package_sha256=package_sha,
    )
    assert verified.signer_key_id == "release-key-1"

    tamper_root = tmp_path / "tampered"
    tamper_root.mkdir()
    policy, provenance, manifest_set, package_sha = _write_signed_provenance(
        tamper_root, tamper=True
    )
    with pytest.raises(AssetError, match="BLOCK_BUILDER_UNTRUSTED"):
        verify_signed_provenance(
            trust_policy_path=policy,
            provenance_path=provenance,
            expected_manifest_set=manifest_set,
            expected_package_sha256=package_sha,
        )


@pytest.mark.parametrize(
    "value",
    [
        {"algorithm": "sha1", "hex": "0" * 40},
        {"algorithm": "sha1", "hex": "f" * 40},
        {"algorithm": "sha512", "hex": "1" * 128},
    ],
)
def test_git_oid_rejects_untrusted_forms(value: object) -> None:
    with pytest.raises(AssetError, match="BLOCK_PROVENANCE_INVALID"):
        GitOID.parse(value)


def test_loader_invocation_is_zero_without_authority_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from butler_pc_core.inference import llm_runtime

    path = tmp_path / "model.gguf"
    path.write_bytes(b"not-loaded")
    invocations = 0

    def forbidden_loader(**_kwargs: object) -> object:
        nonlocal invocations
        invocations += 1
        return object()

    monkeypatch.setattr(llm_runtime, "_LLAMA_AVAILABLE", True)
    monkeypatch.setattr(llm_runtime, "Llama", forbidden_loader)
    runtime = llm_runtime.LlmRuntime(model_path=str(path))
    assert runtime.status == "error"
    assert runtime.last_error == "BLOCK_LOADER_AUTHORITY_REQUIRED"
    assert invocations == 0


def test_windows_blocks_until_native_handle_bridge_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from butler_pc_core.assets import snapshot

    source = os.open(os.devnull, os.O_RDONLY)
    try:
        monkeypatch.setattr(snapshot.platform, "system", lambda: "Windows")
        with pytest.raises(AssetError, match="BLOCK_PLATFORM_UNSUPPORTED"):
            snapshot.create_sealed_snapshot(
                source,
                expected_size=0,
                authority_root=None,
            )
    finally:
        os.close(source)
