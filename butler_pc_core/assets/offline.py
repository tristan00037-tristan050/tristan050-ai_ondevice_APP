from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from .context import PlatformAssetContext
from .contracts import ReleaseProfile
from .errors import AssetError, block
from .manifest import parse_manifest
from .path_policy import validate_relative_path
from .service import AssetService

MAX_PACKAGE_ENTRIES = 100_000
MAX_PACKAGE_BYTES = 64 * 1024 * 1024 * 1024
MAX_PACKAGE_COMPRESSION_RATIO = 1_000
MAX_BUILD_CONTEXT_BYTES = 256 * 1024
_OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise block("MANIFEST_BUILD_BINDING_MISMATCH")
        result[key] = value
    return result


def load_build_context(path: Path, profile: str) -> dict[str, object]:
    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise block("MANIFEST_BUILD_BINDING_MISMATCH")
        raw = path.read_bytes()
        if (
            not raw
            or len(raw) > MAX_BUILD_CONTEXT_BYTES
            or raw.startswith(b"\xef\xbb\xbf")
        ):
            raise block("MANIFEST_BUILD_BINDING_MISMATCH")
        text = raw.decode("utf-8")
        if text != unicodedata.normalize("NFC", text):
            raise block("MANIFEST_BUILD_BINDING_MISMATCH")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                block("MANIFEST_BUILD_BINDING_MISMATCH")
            ),
        )
    except AssetError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise block("MANIFEST_BUILD_BINDING_MISMATCH") from exc
    required = {
        "schema_version",
        "build_id",
        "source_commit",
        "source_tree",
        "release_profile",
        "manifest_set_sha256",
        "toolchain",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise block("MANIFEST_BUILD_BINDING_MISMATCH")
    toolchain = value["toolchain"]
    if (
        value["schema_version"] != 1
        or value["release_profile"] != profile
        or not isinstance(value["build_id"], str)
        or not 1 <= len(value["build_id"]) <= 128
        or not isinstance(value["source_commit"], str)
        or not _OID_RE.fullmatch(value["source_commit"])
        or not isinstance(value["source_tree"], str)
        or not _OID_RE.fullmatch(value["source_tree"])
        or not isinstance(value["manifest_set_sha256"], str)
        or not _SHA_RE.fullmatch(value["manifest_set_sha256"])
        or not isinstance(toolchain, dict)
        or not 1 <= len(toolchain) <= 32
        or not all(
            isinstance(key, str)
            and 1 <= len(key) <= 64
            and isinstance(item, str)
            and 1 <= len(item) <= 256
            for key, item in toolchain.items()
        )
    ):
        raise block("MANIFEST_BUILD_BINDING_MISMATCH")
    return value


def _safe_extract_zip(package: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(package) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_PACKAGE_ENTRIES:
                raise block("RESOURCE_LIMIT_EXCEEDED")
            seen: set[str] = set()
            total = 0
            for member in members:
                name = member.filename[:-1] if member.is_dir() else member.filename
                relative = validate_relative_path(name)
                collision_key = unicodedata.normalize("NFC", relative).casefold()
                if collision_key in seen:
                    raise block("PATH_POLICY_VIOLATION")
                seen.add(collision_key)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise block("SYMLINK_REJECTED")
                total += member.file_size
                if (
                    total > MAX_PACKAGE_BYTES
                    or (
                        member.compress_size == 0
                        and member.file_size > 0
                    )
                    or (
                        member.compress_size > 0
                        and member.file_size
                        > member.compress_size * MAX_PACKAGE_COMPRESSION_RATIO
                    )
                ):
                    raise block("RESOURCE_LIMIT_EXCEEDED")
                target = destination.joinpath(*relative.split("/"))
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    if target.is_symlink() or not target.is_dir():
                        raise block("SYMLINK_REJECTED")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(
                    target,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                )
                try:
                    with archive.open(member) as source, os.fdopen(
                        descriptor, "wb", closefd=True
                    ) as output:
                        descriptor = -1
                        remaining = member.file_size
                        while remaining:
                            chunk = source.read(min(8 * 1024 * 1024, remaining))
                            if not chunk:
                                raise block("FORMAT_SCHEMA_INVALID")
                            output.write(chunk)
                            remaining -= len(chunk)
                        if source.read(1):
                            raise block("FORMAT_SCHEMA_INVALID")
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
    except AssetError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise block("VERIFY_IO_ERROR") from exc


def _locate_resources(package_root: Path) -> Path:
    candidates = [
        package_root,
        package_root / "Contents/Resources",
    ]
    candidates.extend(
        path.parent
        for path in package_root.glob("*.app/Contents/Resources/assets")
    )
    valid: list[Path] = []
    for candidate in candidates:
        assets = candidate / "assets"
        if not assets.is_dir():
            continue
        current = assets
        while current != package_root:
            if current.is_symlink():
                raise block("SYMLINK_REJECTED")
            current = current.parent
        valid.append(candidate)
    unique = {candidate.absolute() for candidate in valid}
    if len(unique) != 1:
        raise block("MANIFEST_MISSING")
    return next(iter(unique))


def _expected_asset_files(resources_root: Path) -> tuple[set[str], int]:
    assets_root = resources_root / "assets"
    manifests_root = assets_root / "manifests"
    try:
        manifest_paths = sorted(manifests_root.glob("*.manifest.json"))
    except OSError as exc:
        raise block("MANIFEST_MISSING") from exc
    if not manifest_paths:
        raise block("MANIFEST_MISSING")
    expected = {"ASSET_BUILD_CONTEXT.json"}
    manifest_count = 0
    for manifest_path in manifest_paths:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise block("SYMLINK_REJECTED")
        raw = manifest_path.read_bytes()
        manifest = parse_manifest(raw)
        expected.add(f"manifests/{manifest.asset_group}.manifest.json")
        if manifest_path.name != f"{manifest.asset_group}.manifest.json":
            raise block("MANIFEST_SCHEMA_INVALID")
        manifest_count += 1
        for entry in manifest.entries:
            expected.add(f"data/{manifest.asset_group}/{entry.relative_path}")
    return expected, manifest_count


def _verify_exact_asset_closure(resources_root: Path) -> int:
    assets_root = resources_root / "assets"
    expected, manifest_count = _expected_asset_files(resources_root)
    actual: set[str] = set()
    folded: set[str] = set()
    try:
        for path in assets_root.rglob("*"):
            relative = path.relative_to(assets_root).as_posix()
            collision_key = unicodedata.normalize("NFC", relative).casefold()
            if collision_key in folded:
                raise block("PATH_POLICY_VIOLATION")
            folded.add(collision_key)
            info = path.lstat()
            if path.is_symlink():
                raise block("SYMLINK_REJECTED")
            if path.is_dir():
                continue
            if not stat.S_ISREG(info.st_mode):
                raise block("NOT_REGULAR_FILE")
            if info.st_mode & 0o111:
                raise block("UNSAFE_SERIALIZATION")
            actual.add(relative)
    except AssetError:
        raise
    except OSError as exc:
        raise block("VERIFY_IO_ERROR") from exc
    if actual != expected:
        raise block("ARCHIVE_INVENTORY_MISMATCH")
    return manifest_count


def verify_release_package(
    *,
    package: Path,
    build_context: Path | None,
    release_profile: str,
) -> int:
    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        if package.is_symlink():
            raise block("SYMLINK_REJECTED")
        if package.is_dir():
            package_root = package
        elif package.is_file() and package.suffix.casefold() == ".zip":
            temporary = tempfile.TemporaryDirectory(prefix="butler-asset-package-")
            package_root = Path(temporary.name)
            _safe_extract_zip(package, package_root)
        else:
            raise block("UNSUPPORTED_FORMAT")
        resources_root = _locate_resources(package_root)
        embedded_context_path = resources_root / "assets/ASSET_BUILD_CONTEXT.json"
        embedded = load_build_context(embedded_context_path, release_profile)
        if build_context is not None:
            external = load_build_context(build_context, release_profile)
            if external != embedded:
                raise block("MANIFEST_BUILD_BINDING_MISMATCH")
        manifest_count = _verify_exact_asset_closure(resources_root)
        context = PlatformAssetContext(
            resource_root=resources_root,
            app_data_root=resources_root,
            release_profile=ReleaseProfile(release_profile),
            build_id=str(embedded["build_id"]),
            source_commit=str(embedded["source_commit"]),
            source_tree=str(embedded["source_tree"]),
            manifest_set_sha256=str(embedded["manifest_set_sha256"]),
            native_authority=True,
        )
        service = AssetService(context)
        service.enforce_profile_contract(release_profile)
        receipts = service.verify_all_groups()
        if len(receipts) != manifest_count:
            raise block("REQUIRED_ASSET_MISSING")
        return len(receipts)
    finally:
        if temporary is not None:
            temporary.cleanup()
