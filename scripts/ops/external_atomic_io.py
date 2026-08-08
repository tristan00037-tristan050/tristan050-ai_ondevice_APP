#!/usr/bin/env python3
"""Descriptor-anchored atomic byte writer for external Butler evidence.

The public CLI is intentionally meta-only.  It never prints a path, payload,
exception, or traceback.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath


DEFAULT_MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


class ExternalWriteError(Exception):
    """A stable fail-closed error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExternalWriteResult:
    sha256: str
    byte_count: int
    final_device: int
    final_inode: int


class _QuietArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ExternalWriteError("OUTPUT_ARGUMENT_INVALID")


def _require_platform() -> None:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ExternalWriteError("OUTPUT_PLATFORM_UNSUPPORTED")
    required = (os.open, os.stat, os.rename, os.unlink)
    if any(item not in os.supports_dir_fd for item in required):
        raise ExternalWriteError("OUTPUT_PLATFORM_UNSUPPORTED")


def _canonical_parts(value: Path, *, absolute_error: str) -> tuple[str, ...]:
    raw = os.fspath(value)
    pure = PurePath(raw)
    if not pure.is_absolute():
        raise ExternalWriteError(absolute_error)
    if "\x00" in raw or raw != os.path.normpath(raw):
        raise ExternalWriteError("OUTPUT_PATH_INVALID_COMPONENT")
    parts = tuple(pure.parts[1:])
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ExternalWriteError("OUTPUT_PATH_INVALID_COMPONENT")
    return parts


def _open_absolute_directory(value: Path) -> int:
    parts = _canonical_parts(value, absolute_error="OUTPUT_PATH_NOT_ABSOLUTE")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    try:
        for component in parts:
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT") from exc
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative_directory(root_descriptor: int, parts: tuple[str, ...]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.dup(root_descriptor)
    try:
        for component in parts:
            try:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
            except OSError as exc:
                raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT") from exc
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _identity(descriptor: int) -> tuple[int, int]:
    current = os.fstat(descriptor)
    return current.st_dev, current.st_ino


def _descriptor_is_within(child_descriptor: int, ancestor_descriptor: int) -> bool:
    """Determine ancestry by directory descriptors, never by string prefix."""
    target = _identity(ancestor_descriptor)
    current = os.dup(child_descriptor)
    try:
        while True:
            here = _identity(current)
            if here == target:
                return True
            parent = os.open(
                "..",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            parent_identity = _identity(parent)
            if parent_identity == here:
                os.close(parent)
                return False
            os.close(current)
            current = parent
    finally:
        os.close(current)


def _relative_output_parts(
    *, evidence_parts: tuple[str, ...], output_parts: tuple[str, ...]
) -> tuple[str, ...]:
    if len(output_parts) <= len(evidence_parts):
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    if output_parts[: len(evidence_parts)] != evidence_parts:
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    relative = output_parts[len(evidence_parts) :]
    if not relative:
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    return relative


def _require_private_root(descriptor: int) -> None:
    root_stat = os.fstat(descriptor)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")
    if stat.S_IMODE(root_stat.st_mode) != 0o700:
        raise ExternalWriteError("OUTPUT_ROOT_MODE_INVALID")
    if hasattr(os, "geteuid") and root_stat.st_uid != os.geteuid():
        raise ExternalWriteError("OUTPUT_ROOT_OWNER_INVALID")


def _revalidate_chain(
    *,
    evidence_root: Path,
    root_descriptor: int,
    parent_parts: tuple[str, ...],
    parent_descriptor: int,
) -> None:
    checked_root = _open_absolute_directory(evidence_root)
    checked_parent = -1
    try:
        if _identity(checked_root) != _identity(root_descriptor):
            raise ExternalWriteError("OUTPUT_ROOT_REPLACED")
        checked_parent = _open_relative_directory(checked_root, parent_parts)
        if _identity(checked_parent) != _identity(parent_descriptor):
            raise ExternalWriteError("OUTPUT_PARENT_REPLACED")
    finally:
        if checked_parent >= 0:
            os.close(checked_parent)
        os.close(checked_root)


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise ExternalWriteError("OUTPUT_WRITE_FAILED")
        remaining = remaining[written:]


def _read_exact(descriptor: int, expected_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= expected_bytes:
        chunk = os.read(descriptor, min(1024 * 1024, expected_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    raw = b"".join(chunks)
    if len(raw) != expected_bytes:
        raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
    return raw


def write_external_bytes_atomic(
    *,
    repo_root: Path,
    evidence_root: Path,
    output: Path,
    payload: bytes,
    max_payload_bytes: int,
) -> ExternalWriteResult:
    """Atomically replace one external evidence file using verified dirfds."""
    _require_platform()
    if not isinstance(payload, bytes):
        raise ExternalWriteError("OUTPUT_PAYLOAD_TYPE_INVALID")
    if max_payload_bytes < 0 or len(payload) > max_payload_bytes:
        raise ExternalWriteError("OUTPUT_PAYLOAD_TOO_LARGE")

    _canonical_parts(repo_root, absolute_error="OUTPUT_PATH_NOT_ABSOLUTE")
    evidence_parts = _canonical_parts(
        evidence_root, absolute_error="OUTPUT_PATH_NOT_ABSOLUTE"
    )
    output_parts = _canonical_parts(output, absolute_error="OUTPUT_PATH_NOT_ABSOLUTE")
    relative = _relative_output_parts(
        evidence_parts=evidence_parts, output_parts=output_parts
    )
    parent_parts, filename = relative[:-1], relative[-1]

    repo_descriptor = _open_absolute_directory(repo_root)
    root_descriptor = _open_absolute_directory(evidence_root)
    parent_descriptor = -1
    temporary_name = f".{filename}.butler-{secrets.token_hex(16)}.tmp"
    temporary_created = False
    final_installed = False
    try:
        _require_private_root(root_descriptor)
        if _descriptor_is_within(root_descriptor, repo_descriptor):
            raise ExternalWriteError("OUTPUT_PATH_INSIDE_REPOSITORY")
        parent_descriptor = _open_relative_directory(root_descriptor, parent_parts)

        try:
            existing = os.stat(filename, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE") from exc
        if existing is not None and (
            not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1
        ):
            raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            temporary_descriptor = os.open(
                temporary_name, flags, 0o600, dir_fd=parent_descriptor
            )
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_WRITE_FAILED") from exc
        temporary_created = True
        try:
            temporary_stat = os.fstat(temporary_descriptor)
            if (
                not stat.S_ISREG(temporary_stat.st_mode)
                or temporary_stat.st_nlink != 1
                or stat.S_IMODE(temporary_stat.st_mode) != 0o600
            ):
                raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")
            _write_all(temporary_descriptor, payload)
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)

        _revalidate_chain(
            evidence_root=evidence_root,
            root_descriptor=root_descriptor,
            parent_parts=parent_parts,
            parent_descriptor=parent_descriptor,
        )
        os.rename(
            temporary_name,
            filename,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_created = False
        final_installed = True
        os.fsync(parent_descriptor)
        _revalidate_chain(
            evidence_root=evidence_root,
            root_descriptor=root_descriptor,
            parent_parts=parent_parts,
            parent_descriptor=parent_descriptor,
        )

        try:
            final_descriptor = os.open(
                filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_descriptor
            )
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH") from exc
        try:
            final_stat = os.fstat(final_descriptor)
            if (
                not stat.S_ISREG(final_stat.st_mode)
                or final_stat.st_nlink != 1
                or stat.S_IMODE(final_stat.st_mode) != 0o600
                or (final_stat.st_dev, final_stat.st_ino)
                != (temporary_stat.st_dev, temporary_stat.st_ino)
            ):
                raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
            reopened = _read_exact(final_descriptor, len(payload))
        finally:
            os.close(final_descriptor)
        if reopened != payload:
            raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
        result = ExternalWriteResult(
            sha256=hashlib.sha256(reopened).hexdigest(),
            byte_count=len(reopened),
            final_device=final_stat.st_dev,
            final_inode=final_stat.st_ino,
        )
        final_installed = False
        return result
    finally:
        if temporary_created and parent_descriptor >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if final_installed and parent_descriptor >= 0:
            try:
                os.unlink(filename, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
            except OSError:
                pass
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        os.close(root_descriptor)
        os.close(repo_descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = _QuietArgumentParser(add_help=False)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-payload-bytes", type=int, required=True)
    try:
        arguments = parser.parse_args(argv)
        if arguments.max_payload_bytes < 0:
            raise ExternalWriteError("OUTPUT_ARGUMENT_INVALID")
        payload = sys.stdin.buffer.read(arguments.max_payload_bytes + 1)
        result = write_external_bytes_atomic(
            repo_root=Path(arguments.repo_root),
            evidence_root=Path(arguments.evidence_root),
            output=Path(arguments.output),
            payload=payload,
            max_payload_bytes=arguments.max_payload_bytes,
        )
    except ExternalWriteError as exc:
        print("EXTERNAL_BYTES_WRITTEN=0")
        print(f"ERROR_CODE={exc.code}")
        return 1
    except (OSError, ValueError):
        print("EXTERNAL_BYTES_WRITTEN=0")
        print("ERROR_CODE=OUTPUT_WRITE_FAILED")
        return 1
    print("EXTERNAL_BYTES_WRITTEN=1")
    print(f"OUTPUT_SHA256={result.sha256}")
    print(f"OUTPUT_BYTES={result.byte_count}")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
