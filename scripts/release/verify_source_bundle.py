#!/usr/bin/env python3
"""Verify and safely extract a Butler source archive without relying on ``.git``."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from scripts.release.firstscreen_source_contracts import (
        PORTABLE_PATH_POLICY,
        SourceContractError,
        portable_path_key,
        require_portable_unique,
        safe_relative_path,
        validate_protected_scope,
    )
except ModuleNotFoundError:  # Standalone product-bundle layout.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from FIRSTSCREEN_SOURCE_CONTRACTS import (  # type: ignore[no-redef]
        PORTABLE_PATH_POLICY,
        SourceContractError,
        portable_path_key,
        require_portable_unique,
        safe_relative_path,
        validate_protected_scope,
    )

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRY_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
MAX_ARCHIVE_ENTRIES = 20_000
STREAM_CHUNK_BYTES = 1024 * 1024


class SourceBundleVerificationError(RuntimeError):
    """Stable, non-sensitive source bundle verification failure."""


class ArchiveHandle:
    """Own the descriptor, file object and ZipFile as one security lifetime."""

    def __init__(
        self,
        descriptor: int,
        file_object: BinaryIO,
        archive: zipfile.ZipFile,
        identity: tuple[int, int, int, int],
    ) -> None:
        self.descriptor = descriptor
        self.file_object = file_object
        self.archive = archive
        self.identity = identity

    def close(self) -> None:
        try:
            self.archive.close()
        finally:
            try:
                self.file_object.close()
            finally:
                os.close(self.descriptor)

    def __enter__(self) -> "ArchiveHandle":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def assert_unchanged(self) -> None:
        current = os.fstat(self.descriptor)
        identity = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        if identity != self.identity:
            raise SourceBundleVerificationError("BLOCK_ARCHIVE_IDENTITY")


def open_verified_archive(path: Path) -> ArchiveHandle:
    """Open an archive exactly once and bind all later work to that object."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    file_object: BinaryIO | None = None
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 0 < metadata.st_size <= MAX_ARCHIVE_BYTES
            or metadata.st_mode & 0o022
            or _is_windows_reparse(metadata)
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise SourceBundleVerificationError("BLOCK_ARCHIVE_IDENTITY")
        identity = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        file_object = os.fdopen(os.dup(descriptor), "rb", closefd=True)
        archive = zipfile.ZipFile(file_object, "r")
        return ArchiveHandle(descriptor, file_object, archive, identity)
    except SourceBundleVerificationError:
        if file_object is not None:
            file_object.close()
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if file_object is not None:
            file_object.close()
        if descriptor >= 0:
            os.close(descriptor)
        raise SourceBundleVerificationError("BLOCK_ARCHIVE_OPEN") from exc


def _git_object_id(kind: str, payload: bytes) -> str:
    header = f"{kind} {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _safe_relative_path(raw: object) -> PurePosixPath:
    try:
        return safe_relative_path(raw)
    except SourceContractError as exc:
        raise SourceBundleVerificationError(str(exc)) from exc


def _portable_path_key(raw: str) -> str:
    try:
        return portable_path_key(raw)
    except SourceContractError as exc:
        raise SourceBundleVerificationError(str(exc)) from exc


def _require_portable_unique(paths: list[str], code: str) -> None:
    try:
        require_portable_unique(paths, code)
    except SourceContractError as exc:
        raise SourceBundleVerificationError(str(exc)) from exc


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _load_manifest(manifest_path: Path) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    try:
        metadata = manifest_path.lstat()
        if manifest_path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ENTRY_BYTES:
            raise SourceBundleVerificationError("MANIFEST_TYPE_INVALID")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBundleVerificationError("MANIFEST_UNREADABLE") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "butler.safe-source-manifest.v2"
        or manifest.get("portable_path_policy") != PORTABLE_PATH_POLICY
    ):
        raise SourceBundleVerificationError("MANIFEST_SCHEMA_INVALID")
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("tracked_regular_file_count") != len(files):
        raise SourceBundleVerificationError("MANIFEST_COUNT_MISMATCH")
    paths: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            raise SourceBundleVerificationError("INVALID_FILE_RECORD")
        path = _safe_relative_path(item.get("path")).as_posix()
        mode = item.get("mode")
        blob = item.get("blob")
        digest = item.get("sha256")
        size = item.get("size")
        if (
            mode not in {"100644", "100755"}
            or not isinstance(blob, str)
            or len(blob) != 40
            or any(character not in "0123456789abcdef" for character in blob)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(size, int)
            or size < 0
            or size > MAX_ENTRY_BYTES
        ):
            raise SourceBundleVerificationError("INVALID_FILE_RECORD")
        paths.append(path)
    canonical = sorted(paths, key=lambda value: value.encode("utf-8"))
    if paths != canonical or len(paths) != len(set(paths)):
        raise SourceBundleVerificationError("MANIFEST_PATH_ORDER_INVALID")
    _require_portable_unique(paths, "MANIFEST_PORTABLE_PATH_COLLISION")
    excluded = manifest.get("excluded")
    if not isinstance(excluded, list) or manifest.get("excluded_count") != len(excluded):
        raise SourceBundleVerificationError("MANIFEST_EXCLUDED_COUNT_MISMATCH")
    excluded_paths: list[str] = []
    for item in excluded:
        if not isinstance(item, dict) or set(item) != {
            "path", "reason", "mode", "object_type", "blob",
        }:
            raise SourceBundleVerificationError("INVALID_EXCLUDED_RECORD")
        path = _safe_relative_path(item.get("path")).as_posix()
        mode = item.get("mode")
        object_type = item.get("object_type")
        reason = item.get("reason")
        blob = item.get("blob")
        if (
            mode not in {"100644", "100755", "120000", "160000"}
            or object_type not in {"blob", "commit"}
            or (mode == "160000") != (object_type == "commit")
            or reason not in {
                "SYMLINK_EXCLUDED", "NON_REGULAR_EXCLUDED", "BANNED_PATH_EXCLUDED",
            }
            or not _is_lower_hex(blob, 40)
        ):
            raise SourceBundleVerificationError("INVALID_EXCLUDED_RECORD")
        excluded_paths.append(path)
    excluded_canonical = sorted(excluded_paths, key=lambda value: value.encode("utf-8"))
    if excluded_paths != excluded_canonical or len(excluded_paths) != len(set(excluded_paths)):
        raise SourceBundleVerificationError("MANIFEST_EXCLUDED_PATH_ORDER_INVALID")
    if set(paths) & set(excluded_paths):
        raise SourceBundleVerificationError("MANIFEST_PATH_DUPLICATE")
    try:
        validate_protected_scope(
            manifest.get("protected_scope"),
            target_commit=manifest.get("commit"),
            manifest_files=files,
        )
    except SourceContractError as exc:
        raise SourceBundleVerificationError(str(exc)) from exc
    return manifest, manifest_bytes, files


def _reconstruct_tree(files: list[dict[str, Any]]) -> str:
    directories: dict[tuple[str, ...], dict[str, tuple[str, str]]] = {}
    for item in files:
        path = _safe_relative_path(item["path"])
        parent = tuple(path.parts[:-1])
        entries = directories.setdefault(parent, {})
        if path.name in entries:
            raise SourceBundleVerificationError("MANIFEST_PATH_DUPLICATE")
        entries[path.name] = (item["mode"], item["blob"])
        for depth in range(len(parent)):
            directories.setdefault(parent[:depth], {})

    tree_ids: dict[tuple[str, ...], str] = {}
    for directory in sorted(directories, key=len, reverse=True):
        entries = dict(directories[directory])
        for child in [candidate for candidate in tree_ids if candidate[:-1] == directory]:
            if child[-1] in entries:
                raise SourceBundleVerificationError("GIT_TREE_NAME_COLLISION")
            entries[child[-1]] = ("40000", tree_ids[child])
        ordered = sorted(
            entries.items(),
            key=lambda pair: pair[0].encode("utf-8") + (b"/" if pair[1][0] == "40000" else b""),
        )
        body = b"".join(
            mode.encode("ascii") + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(oid)
            for name, (mode, oid) in ordered
        )
        tree_ids[directory] = _git_object_id("tree", body)
    return tree_ids.get((), _git_object_id("tree", b""))


def _expected_entries(manifest: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected = {f"source/{item['path']}": item for item in files}
    build = manifest.get("build_stamp")
    if (
        not isinstance(build, dict)
        or build.get("path") != "source/BUILD_INFO.json"
        or not isinstance(build.get("size"), int)
        or not isinstance(build.get("sha256"), str)
    ):
        raise SourceBundleVerificationError("BUILD_STAMP_CONTRACT_INVALID")
    expected["source/BUILD_INFO.json"] = {
        "mode": "100644",
        "size": build["size"],
        "sha256": build["sha256"],
        "generated": True,
    }
    return expected


def _verify_open_archive(
    handle: ArchiveHandle,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    files: list[dict[str, Any]],
) -> tuple[dict[str, zipfile.ZipInfo], dict[str, dict[str, Any]]]:
    expected = _expected_entries(manifest, files)
    expected["SOURCE_ARCHIVE_MANIFEST.json"] = {
        "mode": "100644",
        "size": len(manifest_bytes),
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "generated": True,
    }
    try:
        handle.assert_unchanged()
        infos = handle.archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise SourceBundleVerificationError("BLOCK_ARCHIVE_ENTRY_SET")
        _require_portable_unique(names, "BLOCK_ARCHIVE_DUPLICATE_OR_COLLISION")
        expanded = 0
        compressed = 0
        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            _safe_relative_path(info.filename)
            if info.flag_bits & 0x1:
                raise SourceBundleVerificationError("SOURCE_ARCHIVE_ENCRYPTED")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
            file_type = (info.external_attr >> 16) & 0o170000
            mode = (info.external_attr >> 16) & 0o777
            required = 0o755 if expected[info.filename]["mode"] == "100755" else 0o644
            if file_type != stat.S_IFREG or mode != required:
                raise SourceBundleVerificationError("SOURCE_ARCHIVE_MODE_MISMATCH")
            if info.file_size < 0 or info.file_size > MAX_ENTRY_BYTES or info.compress_size < 0:
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
            expanded += info.file_size
            compressed += info.compress_size
            if expanded > MAX_EXPANDED_BYTES or compressed > MAX_ARCHIVE_BYTES:
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
            if info.file_size and (
                not info.compress_size or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
            record = expected[info.filename]
            digest = hashlib.sha256()
            blob_digest = hashlib.sha1()
            blob_digest.update(f"blob {record['size']}\0".encode("ascii"))
            actual_size = 0
            manifest_payload = bytearray() if info.filename == "SOURCE_ARCHIVE_MANIFEST.json" else None
            with handle.archive.open(info, "r") as source:
                while True:
                    chunk = source.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    actual_size += len(chunk)
                    if actual_size > record["size"] or actual_size > MAX_ENTRY_BYTES:
                        raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
                    digest.update(chunk)
                    if "blob" in record:
                        blob_digest.update(chunk)
                    if manifest_payload is not None:
                        manifest_payload.extend(chunk)
            if actual_size != record["size"] or digest.hexdigest() != record["sha256"]:
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_ENTRY_DIGEST")
            if manifest_payload is not None and bytes(manifest_payload) != manifest_bytes:
                raise SourceBundleVerificationError("SOURCE_ARCHIVE_MANIFEST_MISMATCH")
            if "blob" in record and blob_digest.hexdigest() != record["blob"]:
                raise SourceBundleVerificationError("SOURCE_ARCHIVE_BLOB_MISMATCH")
            by_name[info.filename] = info
        handle.assert_unchanged()
        return by_name, expected
    except SourceBundleVerificationError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise SourceBundleVerificationError("SOURCE_ARCHIVE_UNREADABLE") from exc


def _verify_archive(
    archive_path: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    files: list[dict[str, Any]],
) -> None:
    """Compatibility verifier; verify+extract callers must retain the handle."""

    with open_verified_archive(archive_path) as handle:
        _verify_open_archive(handle, manifest, manifest_bytes, files)


def _verify_extracted_source(source_root: Path, manifest: dict[str, Any], files: list[dict[str, Any]]) -> None:
    if source_root.is_symlink() or not source_root.is_dir():
        raise SourceBundleVerificationError("SOURCE_ROOT_INVALID")
    expected_paths: set[str] = set()
    for item in files:
        relative = _safe_relative_path(item["path"])
        path = source_root.joinpath(*relative.parts)
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise SourceBundleVerificationError("SOURCE_SET_MISMATCH")
        required_mode = 0o755 if item["mode"] == "100755" else 0o644
        if stat.S_IMODE(metadata.st_mode) != required_mode:
            raise SourceBundleVerificationError("SOURCE_MODE_MISMATCH")
        payload = path.read_bytes()
        expected_paths.add(relative.as_posix())
        if len(payload) != item["size"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise SourceBundleVerificationError("SOURCE_DIGEST_MISMATCH")
        if _git_object_id("blob", payload) != item["blob"]:
            raise SourceBundleVerificationError("GIT_BLOB_MISMATCH")

    build = manifest["build_stamp"]
    stamp_path = source_root / "BUILD_INFO.json"
    stamp_metadata = stamp_path.lstat()
    if (
        stamp_path.is_symlink()
        or not stat.S_ISREG(stamp_metadata.st_mode)
        or stamp_metadata.st_nlink != 1
        or stat.S_IMODE(stamp_metadata.st_mode) != 0o644
    ):
        raise SourceBundleVerificationError("BUILD_STAMP_TYPE_INVALID")
    stamp_bytes = stamp_path.read_bytes()
    if len(stamp_bytes) != build["size"] or hashlib.sha256(stamp_bytes).hexdigest() != build["sha256"]:
        raise SourceBundleVerificationError("BUILD_STAMP_DIGEST_MISMATCH")
    try:
        stamp = json.loads(stamp_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBundleVerificationError("BUILD_STAMP_INVALID") from exc
    if (
        stamp.get("build_base_commit_oid") != manifest.get("commit")
        or stamp.get("build_tree_oid") != manifest.get("tree")
        or build.get("commit") != manifest.get("commit")
        or build.get("tree") != manifest.get("tree")
    ):
        raise SourceBundleVerificationError("BUILD_STAMP_IDENTITY_MISMATCH")

    actual_paths: set[str] = set()
    for path in source_root.rglob("*"):
        metadata = path.lstat()
        if path.is_symlink() or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
            raise SourceBundleVerificationError("NON_REGULAR_SOURCE_ENTRY")
        if stat.S_ISREG(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise SourceBundleVerificationError("SOURCE_HARDLINK_FORBIDDEN")
            actual_paths.add(path.relative_to(source_root).as_posix())
    _require_portable_unique(sorted(actual_paths), "SOURCE_PORTABLE_PATH_COLLISION")
    if actual_paths != expected_paths | {"BUILD_INFO.json"}:
        raise SourceBundleVerificationError("SOURCE_SET_MISMATCH")
    if _reconstruct_tree(files + manifest["excluded"]) != manifest.get("tree"):
        raise SourceBundleVerificationError("GIT_TREE_MISMATCH")


def verify_source_bundle(source_root: Path, manifest_path: Path, archive_path: Path) -> None:
    manifest, manifest_bytes, files = _load_manifest(manifest_path)
    _verify_archive(archive_path, manifest, manifest_bytes, files)
    _verify_extracted_source(source_root, manifest, files)


def _secure_directory_flags() -> int:
    if os.name != "posix" or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        raise SourceBundleVerificationError("EXTRACT_SECURE_DIRFD_UNAVAILABLE")
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not directory or not nofollow:
        raise SourceBundleVerificationError("EXTRACT_SECURE_DIRFD_UNAVAILABLE")
    return os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)


def _open_or_create_directory(parent_fd: int, component: str, flags: int) -> int:
    try:
        descriptor = os.open(component, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(component, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            # A concurrent creator is accepted only if the descriptor-bound open
            # below proves that the resulting entry is a real directory.
            pass
        descriptor = os.open(component, flags, dir_fd=parent_fd)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise SourceBundleVerificationError("EXTRACT_PARENT_INVALID")
    return descriptor


def _write_entry_at(root_fd: int, relative: PurePosixPath, payload: bytes, mode: int) -> None:
    descriptors = [os.dup(root_fd)]
    try:
        flags = _secure_directory_flags()
        for component in relative.parts[:-1]:
            descriptors.append(_open_or_create_directory(descriptors[-1], component, flags))
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0)
        descriptor = os.open(relative.name, file_flags, 0o600, dir_fd=descriptors[-1])
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SourceBundleVerificationError("EXTRACT_TARGET_INVALID")
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _write_streamed_entry_at(
    root_fd: int,
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    record: dict[str, Any],
) -> None:
    relative = _safe_relative_path(info.filename)
    descriptors = [os.dup(root_fd)]
    temporary_name = f".butler-{secrets.token_hex(16)}.part"
    published = False
    try:
        flags = _secure_directory_flags()
        for component in relative.parts[:-1]:
            descriptors.append(_open_or_create_directory(descriptors[-1], component, flags))
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0)
        descriptor = os.open(temporary_name, file_flags, 0o600, dir_fd=descriptors[-1])
        try:
            digest = hashlib.sha256()
            actual_size = 0
            with archive.open(info, "r") as source:
                while True:
                    chunk = source.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    actual_size += len(chunk)
                    if actual_size > record["size"] or actual_size > MAX_ENTRY_BYTES:
                        raise SourceBundleVerificationError("BLOCK_ARCHIVE_LIMIT")
                    view = memoryview(chunk)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise SourceBundleVerificationError("BLOCK_DESTINATION_TRUST")
                        view = view[written:]
                    digest.update(chunk)
            if actual_size != record["size"] or digest.hexdigest() != record["sha256"]:
                raise SourceBundleVerificationError("BLOCK_ARCHIVE_ENTRY_DIGEST")
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SourceBundleVerificationError("BLOCK_DESTINATION_TRUST")
            mode = 0o755 if record["mode"] == "100755" else 0o644
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.stat(relative.name, dir_fd=descriptors[-1], follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise SourceBundleVerificationError("BLOCK_DESTINATION_TRUST")
        os.rename(
            temporary_name,
            relative.name,
            src_dir_fd=descriptors[-1],
            dst_dir_fd=descriptors[-1],
        )
        published = True
        os.fsync(descriptors[-1])
    finally:
        if not published:
            try:
                os.unlink(temporary_name, dir_fd=descriptors[-1])
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _safe_extract(
    handle: ArchiveHandle,
    index: dict[str, zipfile.ZipInfo],
    expected: dict[str, dict[str, Any]],
    destination: Path,
    *,
    manifest_digest: str,
) -> dict[str, Any]:
    """Extract to a hidden staging directory and atomically publish once."""

    directory_flags = _secure_directory_flags()
    parent = destination.parent.resolve(strict=True)
    parent_fd = os.open(parent, directory_flags)
    staging_name = f".{destination.name}.butler-staging-{secrets.token_hex(16)}"
    root_fd = -1
    published = False
    try:
        parent_metadata = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or _is_windows_reparse(parent_metadata)
            or (hasattr(os, "getuid") and parent_metadata.st_uid != os.getuid())
        ):
            raise SourceBundleVerificationError("BLOCK_DESTINATION_TRUST")
        try:
            os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise SourceBundleVerificationError("EXTRACT_DESTINATION_NOT_EMPTY")
        os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        root_fd = os.open(staging_name, directory_flags, dir_fd=parent_fd)
        root_identity = os.fstat(root_fd)
        for name in sorted(index, key=lambda value: value.encode("utf-8")):
            _write_streamed_entry_at(root_fd, handle.archive, index[name], expected[name])
        handle.assert_unchanged()
        current_root = os.fstat(root_fd)
        if (current_root.st_dev, current_root.st_ino) != (root_identity.st_dev, root_identity.st_ino):
            raise SourceBundleVerificationError("BLOCK_DESTINATION_TRUST")
        os.fsync(root_fd)
        os.rename(staging_name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        published = True
        identity_material = ":".join(str(item) for item in handle.identity).encode("ascii")
        return {
            "schema_version": "butler.firstscreen.archive-extract-receipt.v2",
            "archive_identity_digest": hashlib.sha256(identity_material).hexdigest(),
            "manifest_digest": manifest_digest,
            "exact_entry_count": len(index),
            "total_compressed_bytes": sum(item.compress_size for item in index.values()),
            "total_uncompressed_bytes": sum(item.file_size for item in index.values()),
            "extracted_file_count": len(index),
            "destination_tree_digest": hashlib.sha256(
                json.dumps(
                    {name: expected[name]["sha256"] for name in sorted(expected)},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "limit_policy_digest": hashlib.sha256(
                f"{MAX_ARCHIVE_BYTES}:{MAX_ARCHIVE_ENTRIES}:{MAX_ENTRY_BYTES}:{MAX_EXPANDED_BYTES}:{MAX_COMPRESSION_RATIO}".encode("ascii")
            ).hexdigest(),
            "platform": platform.system().lower(),
            "terminal_result": "VERIFIED_AND_PUBLISHED",
        }
    finally:
        if root_fd >= 0:
            os.close(root_fd)
        if not published:
            # The random, owner-only staging directory is an explicit
            # quarantine.  It is never exposed at the requested destination.
            try:
                os.rename(
                    staging_name,
                    f"{staging_name}.quarantine",
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
            except OSError:
                pass
        os.close(parent_fd)


def _is_windows_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-root", type=Path)
    source.add_argument("--extract-to", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        manifest_path = arguments.manifest.resolve()
        archive_path = arguments.archive.resolve()
        manifest, manifest_bytes, files = _load_manifest(manifest_path)
        with open_verified_archive(archive_path) as handle:
            index, expected = _verify_open_archive(handle, manifest, manifest_bytes, files)
            if arguments.extract_to is not None:
                extraction_root = arguments.extract_to.absolute()
                _safe_extract(
                    handle,
                    index,
                    expected,
                    extraction_root,
                    manifest_digest=hashlib.sha256(manifest_bytes).hexdigest(),
                )
            else:
                _verify_extracted_source(arguments.source_root.resolve(), manifest, files)
    except Exception:
        print("SOURCE_BUNDLE_VERIFY_OK=0 ERROR_CODE=SOURCE_BUNDLE_INVALID")
        return 1
    print("SOURCE_BUNDLE_VERIFY_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
