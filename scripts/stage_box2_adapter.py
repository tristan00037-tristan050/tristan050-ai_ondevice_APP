#!/usr/bin/env python3
"""Validate and atomically stage the Box2 adapter into Tauri resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REWRITE_ADAPTER_RELATIVE = PurePosixPath(
    "rewrite/adapter/box2b_v5_rewrite"
)
WEIGHTS_NAME = "adapter_model.safetensors"
CONFIG_NAME = "adapter_config.json"
BUFFER_SIZE = 1024 * 1024


class StageError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceEntry:
    relative_path: PurePosixPath
    source_path: Path


@dataclass(frozen=True)
class StageReceipt:
    file_count: int
    total_bytes: int
    manifest_sha256: str
    rewrite_weight_sha256: str


def _sha256_is_valid(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _regular_file_entries(source: Path) -> list[SourceEntry]:
    try:
        root_stat = source.lstat()
    except FileNotFoundError as exc:
        raise StageError("BOX2_ADAPTER_SOURCE_MISSING") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise StageError("BOX2_ADAPTER_SOURCE_INVALID")

    entries: list[SourceEntry] = []
    for current_root, directory_names, file_names in os.walk(source, followlinks=False):
        current_path = Path(current_root)
        for name in directory_names:
            directory_path = current_path / name
            directory_stat = directory_path.lstat()
            if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
                raise StageError("BOX2_ADAPTER_UNSAFE_ENTRY")
        for name in file_names:
            file_path = current_path / name
            file_stat = file_path.lstat()
            if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
                raise StageError("BOX2_ADAPTER_UNSAFE_ENTRY")
            entries.append(
                SourceEntry(
                    relative_path=PurePosixPath(file_path.relative_to(source).as_posix()),
                    source_path=file_path,
                )
            )
    if not entries:
        raise StageError("BOX2_ADAPTER_SOURCE_EMPTY")
    return sorted(entries, key=lambda item: item.relative_path.as_posix())


def _copy_regular_file(entry: SourceEntry, destination: Path) -> tuple[int, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    descriptor = os.open(entry.source_path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise StageError("BOX2_ADAPTER_UNSAFE_ENTRY")
        destination.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        total_bytes = 0
        with os.fdopen(os.dup(descriptor), "rb", closefd=True) as source_handle:
            with destination.open("xb") as destination_handle:
                while chunk := source_handle.read(BUFFER_SIZE):
                    hasher.update(chunk)
                    destination_handle.write(chunk)
                    total_bytes += len(chunk)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or total_bytes != before.st_size:
            raise StageError("BOX2_ADAPTER_SOURCE_CHANGED")
        destination.chmod(0o644)
        return total_bytes, hasher.hexdigest()
    finally:
        os.close(descriptor)


def _validate_runtime_closure(staged_root: Path, expected_weight_sha256: str) -> str:
    adapter_root = staged_root.joinpath(*REWRITE_ADAPTER_RELATIVE.parts)
    weights_path = adapter_root / WEIGHTS_NAME
    config_path = adapter_root / CONFIG_NAME
    if not weights_path.is_file() or weights_path.is_symlink():
        raise StageError("BOX2_ADAPTER_WEIGHT_MISSING")
    if not config_path.is_file() or config_path.is_symlink():
        raise StageError("BOX2_ADAPTER_CONFIG_MISSING")

    hasher = hashlib.sha256()
    with weights_path.open("rb") as weights_handle:
        while chunk := weights_handle.read(BUFFER_SIZE):
            hasher.update(chunk)
    actual_weight_sha256 = hasher.hexdigest()
    if actual_weight_sha256 != expected_weight_sha256:
        raise StageError("BOX2_ADAPTER_WEIGHT_SHA_MISMATCH")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StageError("BOX2_ADAPTER_CONFIG_INVALID") from exc
    if (
        not isinstance(config, dict)
        or config.get("peft_type") != "LORA"
        or config.get("task_type") != "CAUSAL_LM"
        or config.get("inference_mode") is not True
        or not isinstance(config.get("target_modules"), list)
        or not config["target_modules"]
    ):
        raise StageError("BOX2_ADAPTER_CONFIG_INVALID")
    return actual_weight_sha256


def _manifest_digest(file_digests: list[tuple[str, str]]) -> str:
    hasher = hashlib.sha256()
    for relative_path, file_sha256 in file_digests:
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(file_sha256.encode("ascii"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def stage_box2_adapter(
    source: Path,
    destination: Path,
    *,
    expected_weight_sha256: str,
) -> StageReceipt:
    if not _sha256_is_valid(expected_weight_sha256):
        raise StageError("BOX2_ADAPTER_EXPECTED_SHA_INVALID")
    if destination.is_symlink():
        raise StageError("BOX2_ADAPTER_DESTINATION_UNSAFE")
    if destination.exists() and not destination.is_dir():
        raise StageError("BOX2_ADAPTER_DESTINATION_UNSAFE")

    entries = _regular_file_entries(source)
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".box2-adapter-stage-", dir=destination_parent)
    )
    backup_root: Path | None = None
    file_digests: list[tuple[str, str]] = []
    total_bytes = 0
    try:
        for entry in entries:
            staged_file = staging_root.joinpath(*entry.relative_path.parts)
            file_size, file_sha256 = _copy_regular_file(entry, staged_file)
            total_bytes += file_size
            file_digests.append((entry.relative_path.as_posix(), file_sha256))

        rewrite_weight_sha256 = _validate_runtime_closure(
            staging_root, expected_weight_sha256
        )
        manifest_sha256 = _manifest_digest(file_digests)

        if destination.exists():
            backup_root = destination_parent / (
                f".{destination.name}.backup-{os.getpid()}"
            )
            if backup_root.exists():
                raise StageError("BOX2_ADAPTER_DESTINATION_BUSY")
            os.replace(destination, backup_root)
        try:
            os.replace(staging_root, destination)
            _fsync_directory(destination_parent)
        except Exception:
            if backup_root is not None and backup_root.exists() and not destination.exists():
                os.replace(backup_root, destination)
                _fsync_directory(destination_parent)
            raise
        if backup_root is not None:
            shutil.rmtree(backup_root)
            _fsync_directory(destination_parent)
        return StageReceipt(
            file_count=len(file_digests),
            total_bytes=total_bytes,
            manifest_sha256=manifest_sha256,
            rewrite_weight_sha256=rewrite_weight_sha256,
        )
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-weight-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        receipt = stage_box2_adapter(
            args.source,
            args.destination,
            expected_weight_sha256=args.expected_weight_sha256,
        )
    except StageError as exc:
        print("BOX2_ADAPTER_STAGE_OK=0")
        print(f"ERROR_CODE={exc.code}")
        return 1
    except Exception:
        print("BOX2_ADAPTER_STAGE_OK=0")
        print("ERROR_CODE=BOX2_ADAPTER_STAGE_FAILED")
        return 1

    print("BOX2_ADAPTER_STAGE_OK=1")
    print(f"BOX2_ADAPTER_FILE_COUNT={receipt.file_count}")
    print(f"BOX2_ADAPTER_BYTES={receipt.total_bytes}")
    print(f"BOX2_ADAPTER_MANIFEST_SHA256={receipt.manifest_sha256}")
    print(f"BOX2_REWRITE_WEIGHT_SHA256={receipt.rewrite_weight_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
