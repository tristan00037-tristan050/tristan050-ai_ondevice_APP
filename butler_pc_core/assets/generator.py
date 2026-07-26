from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from .contracts import AssetEntry, FileIdentity
from .errors import AssetError, block
from .formats import validate_format
from .manifest import canonical_json_bytes, manifest_set_root, parse_manifest
from .path_policy import validate_relative_path
from .context import PlatformAssetContext
from .contracts import ReleaseProfile
from .service import AssetService
from .verifier import HASH_CHUNK_BYTES, SafeRoot

MAX_INVENTORY_BYTES = 4 * 1024 * 1024
MAX_GROUPS = 128
_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
_GROUP_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_UNSAFE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".dll",
    ".dylib",
    ".exe",
    ".joblib",
    ".pickle",
    ".pkl",
    ".ps1",
    ".py",
    ".pyc",
    ".sh",
    ".so",
}


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise block("MANIFEST_SCHEMA_INVALID")
        result[key] = value
    return result


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INVENTORY_BYTES:
            raise block("MANIFEST_SCHEMA_INVALID")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if raw.startswith(b"\xef\xbb\xbf") or text != unicodedata.normalize("NFC", text):
            raise block("MANIFEST_SCHEMA_INVALID")
        value = json.loads(text, object_pairs_hook=_no_duplicate_pairs)
    except AssetError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise block("MANIFEST_SCHEMA_INVALID") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "groups"}:
        raise block("MANIFEST_SCHEMA_INVALID")
    if value["schema_version"] != 1 or not isinstance(value["groups"], list):
        raise block("MANIFEST_SCHEMA_INVALID")
    if not 1 <= len(value["groups"]) <= MAX_GROUPS:
        raise block("MANIFEST_SCHEMA_INVALID")
    return value


def _copy_and_measure(source_fd: int, target: Path) -> tuple[int, str]:
    before = FileIdentity.from_stat(os.fstat(source_fd))
    descriptor = os.open(target, _OPEN_FLAGS, 0o400)
    digest = hashlib.sha256()
    total = 0
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            descriptor = -1
            while True:
                chunk = os.read(source_fd, HASH_CHUNK_BYTES)
                if not chunk:
                    break
                destination.write(chunk)
                digest.update(chunk)
                total += len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    after = FileIdentity.from_stat(os.fstat(source_fd))
    if before != after or total != before.size:
        raise block("TOCTOU_CHANGED")
    return total, digest.hexdigest()


def _entry_payload(row: object, source: SafeRoot, data_group: Path) -> dict[str, object]:
    required = {"role", "relative_path", "media_type", "validator"}
    optional = {"allow_empty", "model_identity"}
    if not isinstance(row, dict) or not required <= set(row) or not set(row) <= required | optional:
        raise block("MANIFEST_SCHEMA_INVALID")
    relative = validate_relative_path(row["relative_path"])
    if Path(relative).suffix.casefold() in _UNSAFE_SUFFIXES:
        raise block("UNSAFE_SERIALIZATION")
    role = row["role"]
    media_type = row["media_type"]
    validator = row["validator"]
    if not all(isinstance(value, str) and value for value in (role, media_type, validator)):
        raise block("MANIFEST_SCHEMA_INVALID")
    target = data_group.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = source.open_regular(relative)
    try:
        source_identity = FileIdentity.from_stat(os.fstat(fd))
        if source_identity.link_count != 1 or source_identity.mode & 0o111:
            raise block("UNSAFE_SERIALIZATION")
        size, digest = _copy_and_measure(fd, target)
        duplicate = os.dup(fd)
        with os.fdopen(duplicate, "rb", closefd=True) as handle:
            validate_format(
                handle,
                AssetEntry(
                    role=role,
                    relative_path=relative,
                    size_bytes=size,
                    sha256=digest,
                    media_type=media_type,
                    validator=validator,
                    allow_empty=bool(row.get("allow_empty", False)),
                    model_identity=row.get("model_identity"),
                ),
            )
    finally:
        os.close(fd)
    result: dict[str, object] = {
        "role": role,
        "relative_path": relative,
        "size_bytes": size,
        "sha256": digest,
        "media_type": media_type,
        "validator": validator,
    }
    if row.get("allow_empty") is True:
        result["allow_empty"] = True
    if "model_identity" in row:
        result["model_identity"] = row["model_identity"]
    return result


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for item in sorted(path.rglob("*"), key=lambda candidate: len(candidate.parts), reverse=True):
        try:
            item.chmod(0o700 if item.is_dir() else 0o600)
        except OSError:
            pass
    try:
        path.chmod(0o700)
    except OSError:
        pass
    shutil.rmtree(path)


def _fsync_tree(root: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in files:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    for path in [*directories, root]:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def stage_assets(
    *,
    source_root: Path,
    inventory_path: Path,
    resources_root: Path,
    source_commit: str,
    source_tree: str,
    release_profile: str,
) -> str:
    inventory = _load_inventory(inventory_path)
    resources_root.mkdir(parents=True, exist_ok=True)
    staging_root: Path | None = Path(
        tempfile.mkdtemp(prefix=".assets-stage-", dir=resources_root)
    )
    final = resources_root / "assets"
    try:
        if final.exists() or final.is_symlink():
            raise block("PUBLISH_TARGET_EXISTS")
        candidate = staging_root / "assets"
        candidate.mkdir(mode=0o700)
        manifests_dir = candidate / "manifests"
        data_dir = candidate / "data"
        manifests_dir.mkdir(mode=0o700)
        data_dir.mkdir(mode=0o700)
        manifests = []
        groups_seen: set[str] = set()
        with SafeRoot(source_root) as safe_source:
            for group in inventory["groups"]:
                if not isinstance(group, dict) or set(group) != {
                    "asset_group",
                    "group_version",
                    "required_for_profiles",
                    "entries",
                }:
                    raise block("MANIFEST_SCHEMA_INVALID")
                name = group["asset_group"]
                if (
                    not isinstance(name, str)
                    or not _GROUP_RE.fullmatch(name)
                    or name in groups_seen
                ):
                    raise block("MANIFEST_SCHEMA_INVALID")
                groups_seen.add(name)
                rows = group["entries"]
                if not isinstance(rows, list) or not rows:
                    raise block("MANIFEST_SCHEMA_INVALID")
                relative_keys: set[str] = set()
                for row in rows:
                    if not isinstance(row, dict):
                        raise block("MANIFEST_SCHEMA_INVALID")
                    relative = validate_relative_path(row.get("relative_path"))
                    collision_key = unicodedata.normalize("NFC", relative).casefold()
                    if collision_key in relative_keys:
                        raise block("PATH_POLICY_VIOLATION")
                    relative_keys.add(collision_key)
                target_group = data_dir / name
                target_group.mkdir(mode=0o700)
                entries = sorted(
                    (_entry_payload(row, safe_source, target_group) for row in rows),
                    key=lambda item: str(item["relative_path"]),
                )
                payload = {
                    "schema_version": 1,
                    "asset_group": name,
                    "group_version": group["group_version"],
                    "required_for_profiles": group["required_for_profiles"],
                    "entries": entries,
                }
                raw = canonical_json_bytes(payload)
                manifest = parse_manifest(raw)
                (manifests_dir / f"{name}.manifest.json").write_bytes(raw)
                manifests.append(manifest)
        root_digest = manifest_set_root(manifests)
        context = {
            "schema_version": 1,
            "build_id": source_commit,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "release_profile": release_profile,
            "manifest_set_sha256": root_digest,
            "toolchain": {
                "asset_generator": "butler.assets.v2",
                "python": platform.python_version(),
                "platform": platform.system().lower(),
            },
        }
        (candidate / "ASSET_BUILD_CONTEXT.json").write_bytes(canonical_json_bytes(context))
        verification_context = PlatformAssetContext(
            resource_root=staging_root,
            app_data_root=staging_root,
            release_profile=ReleaseProfile(release_profile),
            build_id=source_commit,
            source_commit=source_commit,
            source_tree=source_tree,
            manifest_set_sha256=root_digest,
            native_authority=True,
        )
        receipts = AssetService(verification_context).verify_required_groups(release_profile)
        expected_required = sum(
            release_profile in manifest.required_for_profiles for manifest in manifests
        )
        if len(receipts) != expected_required:
            raise block("REQUIRED_ASSET_MISSING")
        for file_path in candidate.rglob("*"):
            file_path.chmod(0o500 if file_path.is_dir() else 0o400)
        _fsync_tree(candidate)
        os.replace(candidate, final)
        final.chmod(0o500)
        directory_fd = os.open(resources_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return root_digest
    except Exception:
        raise
    finally:
        if staging_root is not None and staging_root.exists():
            try:
                _remove_tree(staging_root)
            except OSError:
                pass
