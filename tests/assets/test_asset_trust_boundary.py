from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import struct
import threading
import zipfile
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from butler_pc_core.assets.context import (
    PlatformAssetContext,
    parse_platform_context,
    read_native_bootstrap,
)
from butler_pc_core.assets.contracts import AssetEntry, AssetManifest, ReleaseProfile
from butler_pc_core.assets.errors import AssetError
from butler_pc_core.assets.formats import validate_format
from butler_pc_core.assets.generator import stage_assets
from butler_pc_core.assets.manifest import canonical_json_bytes, parse_manifest
from butler_pc_core.assets.offline import verify_release_package
from butler_pc_core.assets.path_policy import validate_relative_path
from butler_pc_core.assets.resolver import AssetResolver
from butler_pc_core.assets.service import AssetService
from butler_pc_core.assets.verifier import SafeRoot, verify_entry
from butler_pc_core.helper1 import memory_helper

pytestmark = pytest.mark.no_sidecar_token


def _inventory() -> dict[str, object]:
    return {
        "schema_version": 1,
        "groups": [
            {
                "asset_group": "helper1.search",
                "group_version": 1,
                "required_for_profiles": ["test"],
                "entries": [
                    {
                        "role": "chunks_jsonl",
                        "relative_path": "helper1/chunks.jsonl",
                        "media_type": "application/jsonl",
                        "validator": "jsonl",
                    },
                    {
                        "role": "embeddings_npy",
                        "relative_path": "helper1/embeddings.npy",
                        "media_type": "application/x-npy",
                        "validator": "npy",
                    },
                ],
            }
        ],
    }


def _stage(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    resources = tmp_path / "resources"
    (source / "helper1").mkdir(parents=True)
    (source / "helper1/chunks.jsonl").write_text(
        '{"chunk_id":"one","text":"alpha contract"}\n'
        '{"chunk_id":"two","text":"beta invoice"}\n',
        encoding="utf-8",
    )
    np.save(
        source / "helper1/embeddings.npy",
        np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        allow_pickle=False,
    )
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(canonical_json_bytes(_inventory()))
    digest = stage_assets(
        source_root=source,
        inventory_path=inventory,
        resources_root=resources,
        source_commit="1" * 40,
        source_tree="2" * 40,
        release_profile="test",
    )
    return resources, digest


def _context(resources: Path, digest: str) -> PlatformAssetContext:
    return PlatformAssetContext(
        resource_root=resources,
        app_data_root=resources,
        release_profile=ReleaseProfile.TEST,
        build_id="1" * 40,
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256=digest,
        native_authority=True,
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../asset",
        "/asset",
        "~/asset",
        "C:/asset",
        "\\\\server\\share",
        "a\\b",
        "a:b",
        "a//b",
        "a/",
        "CON",
        "dir/NUL.txt",
        "trailing.",
        "trailing ",
        "a/\x00b",
    ],
)
def test_strict_relative_path_blocks_lexical_attacks(value: str) -> None:
    with pytest.raises(AssetError, match="PATH_POLICY_VIOLATION"):
        validate_relative_path(value)


def test_manifest_rejects_duplicates_unknown_fields_and_unsorted_entries() -> None:
    duplicate = (
        b'{"schema_version":1,"schema_version":1,"asset_group":"x",'
        b'"group_version":1,"required_for_profiles":[],"entries":[]}'
    )
    with pytest.raises(AssetError, match="MANIFEST_SCHEMA_INVALID"):
        parse_manifest(duplicate)

    payload = _inventory()["groups"][0]
    assert isinstance(payload, dict)
    manifest = {
        "schema_version": 1,
        "asset_group": payload["asset_group"],
        "group_version": 1,
        "required_for_profiles": ["test"],
        "entries": [
            {
                "role": "z",
                "relative_path": "z.npy",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "media_type": "application/x-npy",
                "validator": "npy",
            },
            {
                "role": "a",
                "relative_path": "a.npy",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "media_type": "application/x-npy",
                "validator": "npy",
            },
        ],
    }
    with pytest.raises(AssetError, match="MANIFEST_SCHEMA_INVALID"):
        parse_manifest(canonical_json_bytes(manifest))
    manifest["unexpected"] = True
    with pytest.raises(AssetError, match="MANIFEST_SCHEMA_INVALID"):
        parse_manifest(canonical_json_bytes(manifest))


def test_committed_manifest_schema_accepts_the_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        (root / "contracts/assets/assets-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {
        "schema_version": 1,
        "asset_group": "helper1.search",
        "group_version": 1,
        "required_for_profiles": ["test"],
        "entries": [
            {
                "role": "chunks_jsonl",
                "relative_path": "helper1/chunks.jsonl",
                "size_bytes": 1,
                "sha256": "0" * 64,
                "media_type": "application/jsonl",
                "validator": "jsonl",
            }
        ],
    }
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    parse_manifest(canonical_json_bytes(payload))


def test_stage_verify_and_helper1_use_same_verified_handles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources, digest = _stage(tmp_path)
    service = AssetService(_context(resources, digest))
    receipts = service.verify_required_groups("test")
    assert len(receipts) == 1
    assert receipts[0].asset_group == "helper1.search"
    monkeypatch.setattr(memory_helper, "get_asset_service", lambda: service)
    results = memory_helper.find("alpha", 2)
    assert len(results) == 2
    assert {item["chunk_id"] for item in results} == {"one", "two"}


def test_native_bootstrap_requires_a_complete_length_prefixed_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("butler_pc_core.assets.context._CONTEXT", None)
    payload = canonical_json_bytes(
        {
            "schema_version": 1,
            "resource_root": str(tmp_path),
            "app_data_root": str(tmp_path),
            "release_profile": "development",
            "build_id": "1" * 40,
            "source_commit": "1" * 40,
            "source_tree": "2" * 40,
            "manifest_set_sha256": None,
        }
    )

    class Stream:
        def __init__(self, raw: bytes) -> None:
            self.buffer = io.BytesIO(raw)

    context = read_native_bootstrap(
        Stream(struct.pack(">I", len(payload)) + payload)  # type: ignore[arg-type]
    )
    assert context.resource_root == tmp_path
    with pytest.raises(AssetError, match="PLATFORM_CONTEXT_INVALID"):
        read_native_bootstrap(
            Stream(struct.pack(">I", len(payload) + 1) + payload)  # type: ignore[arg-type]
        )


def test_group_verification_is_single_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources, digest = _stage(tmp_path)
    service = AssetService(_context(resources, digest))
    calls = 0
    barrier = threading.Barrier(4)
    original = __import__(
        "butler_pc_core.assets.service", fromlist=["verify_entry"]
    ).verify_entry

    def counted(root, entry):
        nonlocal calls
        calls += 1
        return original(root, entry)

    monkeypatch.setattr("butler_pc_core.assets.service.verify_entry", counted)
    receipts: list[tuple] = []

    def verify() -> None:
        barrier.wait()
        receipts.append(service.verify_required_groups("test"))

    threads = [threading.Thread(target=verify) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(receipts) == 4
    assert calls == 2
    assert len({item[0].manifest_digest for item in receipts}) == 1


def test_resolver_rejects_adapter_base_mismatch_and_missing_model_identity() -> None:
    def entry(role: str, *, base: str | None = None, model: bool = False) -> AssetEntry:
        identity = None
        if base is not None or model:
            identity = {
                "model_id": role,
                "version": "1",
                "architecture": "test",
            }
            if base is not None:
                identity["base_model_sha256"] = base
        return AssetEntry(
            role=role,
            relative_path=f"{role}.bin",
            size_bytes=1,
            sha256="a" * 64,
            media_type="application/octet-stream",
            validator="opaque",
            model_identity=identity,
        )

    box2 = AssetManifest(
        asset_group="box2.adapter",
        group_version=1,
        required_for_profiles=("test",),
        entries=(
            entry("base_model"),
            entry("butler_adapter", base="b" * 64),
            entry("rewrite_adapter", base="a" * 64),
        ),
        digest="c" * 64,
    )
    resolver = AssetResolver(
        {"box2.adapter": box2},
        {
            "box2.adapter": (
                "box2.adapter",
                ("base_model", "butler_adapter", "rewrite_adapter"),
            )
        },
    )
    with pytest.raises(AssetError, match="ADAPTER_BASE_MISMATCH"):
        resolver.resolve("box2.adapter")

    helper = AssetManifest(
        asset_group="helper1.ask",
        group_version=1,
        required_for_profiles=("test",),
        entries=(entry("ask_model_gguf"),),
        digest="d" * 64,
    )
    resolver = AssetResolver(
        {"helper1.ask": helper},
        {"helper1.ask": ("helper1.ask", ("ask_model_gguf",))},
    )
    with pytest.raises(AssetError, match="MODEL_IDENTITY_MISMATCH"):
        resolver.resolve("helper1.ask")


def test_middle_byte_tamper_is_blocked(tmp_path: Path) -> None:
    resources, digest = _stage(tmp_path)
    target = resources / "assets/data/helper1.search/helper1/embeddings.npy"
    raw = bytearray(target.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    target.chmod(0o600)
    target.write_bytes(raw)
    with pytest.raises(AssetError, match="FILE_DIGEST_MISMATCH"):
        AssetService(_context(resources, digest)).verify_required_groups("test")


def test_symlink_asset_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    real = tmp_path / "real"
    real.write_bytes(b"safe")
    (root / "asset").symlink_to(real)
    entry = AssetEntry(
        role="data",
        relative_path="asset",
        size_bytes=4,
        sha256=hashlib.sha256(b"safe").hexdigest(),
        media_type="application/octet-stream",
        validator="opaque",
    )
    with SafeRoot(root) as safe:
        with pytest.raises(AssetError, match="SYMLINK_REJECTED"):
            verify_entry(safe, entry)


def test_same_size_toctou_swap_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "asset"
    target.write_bytes(b"safe")
    entry = AssetEntry(
        role="data",
        relative_path="asset",
        size_bytes=4,
        sha256=hashlib.sha256(b"safe").hexdigest(),
        media_type="application/octet-stream",
        validator="opaque",
    )

    def mutate(_handle, _entry) -> None:
        target.write_bytes(b"evil")

    monkeypatch.setattr("butler_pc_core.assets.verifier.validate_format", mutate)
    with SafeRoot(root) as safe:
        with pytest.raises(AssetError, match="TOCTOU_CHANGED"):
            verify_entry(safe, entry)


def test_object_npy_is_rejected_even_when_digest_matches(tmp_path: Path) -> None:
    path = tmp_path / "object.npy"
    np.save(path, np.asarray([{"unsafe": True}], dtype=object), allow_pickle=True)
    entry = AssetEntry(
        role="array",
        relative_path="object.npy",
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        media_type="application/x-npy",
        validator="npy",
    )
    with path.open("rb") as handle:
        with pytest.raises(AssetError, match="UNSAFE_SERIALIZATION"):
            validate_format(handle, entry)


def test_manifest_set_build_binding_mismatch_blocks(tmp_path: Path) -> None:
    resources, _digest = _stage(tmp_path)
    with pytest.raises(AssetError, match="MANIFEST_BUILD_BINDING_MISMATCH"):
        AssetService(_context(resources, "f" * 64)).verify_required_groups("test")


def test_production_context_rejects_non_native_override(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "resource_root": str(tmp_path),
        "app_data_root": str(tmp_path),
        "release_profile": "production",
        "build_id": "1" * 40,
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "manifest_set_sha256": None,
    }
    with pytest.raises(AssetError, match="OVERRIDE_FORBIDDEN"):
        parse_platform_context(canonical_json_bytes(payload), native_authority=False)


def test_production_runtime_blocks_an_incomplete_required_asset_set(
    tmp_path: Path,
) -> None:
    resources, digest = _stage(tmp_path)
    context = PlatformAssetContext(
        resource_root=resources,
        app_data_root=resources,
        release_profile=ReleaseProfile.PRODUCTION,
        build_id="1" * 40,
        source_commit="1" * 40,
        source_tree="2" * 40,
        manifest_set_sha256=digest,
        native_authority=True,
    )
    with pytest.raises(AssetError, match="REQUIRED_ASSET_MISSING"):
        AssetService(context).verify_required_groups("production")


def test_cached_status_contains_no_paths_or_digests(tmp_path: Path) -> None:
    resources, digest = _stage(tmp_path)
    service = AssetService(_context(resources, digest))
    service.verify_required_groups("test")
    payload = service.get_cached_status()
    serialized = json.dumps(payload, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert digest not in serialized
    assert payload["overall_state"] == "AVAILABLE"


def test_offline_verifier_accepts_exact_staged_closure(tmp_path: Path) -> None:
    resources, _digest = _stage(tmp_path)
    count = verify_release_package(
        package=resources,
        build_context=resources / "assets/ASSET_BUILD_CONTEXT.json",
        release_profile="test",
    )
    assert count == 1


def test_offline_verifier_rejects_extra_asset_file(tmp_path: Path) -> None:
    resources, _digest = _stage(tmp_path)
    extra = resources / "assets/data/helper1.search/extra.bin"
    extra.parent.chmod(0o700)
    extra.write_bytes(b"extra")
    with pytest.raises(AssetError, match="ARCHIVE_INVENTORY_MISMATCH"):
        verify_release_package(
            package=resources,
            build_context=resources / "assets/ASSET_BUILD_CONTEXT.json",
            release_profile="test",
        )


def test_zip_package_path_traversal_is_blocked(tmp_path: Path) -> None:
    package = tmp_path / "malicious.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../outside", b"blocked")
    with pytest.raises(AssetError, match="PATH_POLICY_VIOLATION"):
        verify_release_package(
            package=package,
            build_context=None,
            release_profile="test",
        )


def test_generator_rejects_executable_and_dynamic_code_assets(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    executable = source / "payload.bin"
    executable.write_bytes(b"payload")
    executable.chmod(0o700)
    inventory = tmp_path / "inventory.json"
    payload = _inventory()
    payload["groups"][0]["entries"] = [
        {
            "role": "chunks_jsonl",
            "relative_path": "payload.bin",
            "media_type": "application/octet-stream",
            "validator": "opaque",
        }
    ]
    inventory.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(AssetError, match="UNSAFE_SERIALIZATION"):
        stage_assets(
            source_root=source,
            inventory_path=inventory,
            resources_root=tmp_path / "resources",
            source_commit="1" * 40,
            source_tree="2" * 40,
            release_profile="test",
        )

    executable.chmod(0o600)
    dynamic = source / "payload.py"
    dynamic.write_text("raise SystemExit\n", encoding="utf-8")
    payload["groups"][0]["entries"][0]["relative_path"] = "payload.py"
    inventory.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(AssetError, match="UNSAFE_SERIALIZATION"):
        stage_assets(
            source_root=source,
            inventory_path=inventory,
            resources_root=tmp_path / "resources2",
            source_commit="1" * 40,
            source_tree="2" * 40,
            release_profile="test",
        )


def test_generator_refuses_to_replace_a_published_asset_tree(tmp_path: Path) -> None:
    resources, _digest = _stage(tmp_path)
    source = tmp_path / "second-source"
    (source / "helper1").mkdir(parents=True)
    (source / "helper1/chunks.jsonl").write_text(
        '{"chunk_id":"one","text":"new"}\n', encoding="utf-8"
    )
    np.save(
        source / "helper1/embeddings.npy",
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        allow_pickle=False,
    )
    inventory = tmp_path / "second-inventory.json"
    inventory.write_bytes(canonical_json_bytes(_inventory()))
    with pytest.raises(AssetError, match="PUBLISH_TARGET_EXISTS"):
        stage_assets(
            source_root=source,
            inventory_path=inventory,
            resources_root=resources,
            source_commit="1" * 40,
            source_tree="2" * 40,
            release_profile="test",
        )


def test_json_duplicate_keys_and_control_values_are_blocked() -> None:
    entry = AssetEntry(
        role="metadata",
        relative_path="metadata.json",
        size_bytes=0,
        sha256="0" * 64,
        media_type="application/json",
        validator="json",
    )
    for raw in (b'{"a":1,"a":2}', b'{"value":"\\u0000"}'):
        with pytest.raises(AssetError, match="FORMAT_SCHEMA_INVALID"):
            validate_format(io.BytesIO(raw), entry)


def test_npy_trailing_payload_is_blocked() -> None:
    stream = io.BytesIO()
    np.save(stream, np.asarray([1.0, 2.0], dtype=np.float32), allow_pickle=False)
    raw = stream.getvalue() + b"trailing"
    entry = AssetEntry(
        role="array",
        relative_path="array.npy",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type="application/x-npy",
        validator="npy",
    )
    with pytest.raises(AssetError, match="FORMAT_SCHEMA_INVALID"):
        validate_format(io.BytesIO(raw), entry)


def test_npz_member_path_traversal_is_blocked() -> None:
    member = io.BytesIO()
    np.save(member, np.asarray([1.0], dtype=np.float32), allow_pickle=False)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../array.npy", member.getvalue())
    raw = archive.getvalue()
    entry = AssetEntry(
        role="arrays",
        relative_path="arrays.npz",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type="application/x-npz",
        validator="npz",
    )
    with pytest.raises(AssetError, match="FORMAT_SCHEMA_INVALID"):
        validate_format(io.BytesIO(raw), entry)


def test_safetensors_overlapping_offsets_are_blocked() -> None:
    header = canonical_json_bytes(
        {
            "a": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
            "b": {"dtype": "F32", "shape": [1], "data_offsets": [2, 6]},
        }
    )
    raw = struct.pack("<Q", len(header)) + header + b"\0" * 6
    entry = AssetEntry(
        role="weights",
        relative_path="weights.safetensors",
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type="application/safetensors",
        validator="safetensors",
    )
    with pytest.raises(AssetError, match="BLOCK_FORMAT_INVALID"):
        validate_format(io.BytesIO(raw), entry)


def test_hardlinked_asset_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    asset = root / "asset"
    asset.write_bytes(b"safe")
    os.link(asset, tmp_path / "alias")
    entry = AssetEntry(
        role="data",
        relative_path="asset",
        size_bytes=4,
        sha256=hashlib.sha256(b"safe").hexdigest(),
        media_type="application/octet-stream",
        validator="opaque",
    )
    with SafeRoot(root) as safe:
        with pytest.raises(AssetError, match="HARDLINK_REJECTED"):
            verify_entry(safe, entry)


def test_status_projection_requires_session_and_rate_limits(monkeypatch) -> None:
    from fastapi import HTTPException, Request, Response
    from butler_pc_core.assets import status

    class SnapshotService:
        @staticmethod
        def get_cached_status():
            return {"schema_version": 1, "overall_state": "DEGRADED", "groups": []}

    monkeypatch.setattr(status, "get_asset_service", lambda: SnapshotService())
    status._LAST_REQUEST.clear()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/assets/status",
        "headers": [],
        "client": ("testclient", 1234),
    }
    request = Request(scope)
    response = Response()
    with pytest.raises(HTTPException) as missing:
        asyncio.run(status.asset_status(request, response))
    assert missing.value.status_code == 401

    request.state.capability_session_digest = "session-digest"
    payload = asyncio.run(status.asset_status(request, response))
    assert payload["overall_state"] == "DEGRADED"
    assert response.headers["Cache-Control"] == "no-store"
    with pytest.raises(HTTPException) as limited:
        asyncio.run(status.asset_status(request, Response()))
    assert limited.value.status_code == 429
