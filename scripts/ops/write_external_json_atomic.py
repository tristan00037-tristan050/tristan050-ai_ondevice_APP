#!/usr/bin/env python3
"""Race-resistant writer for AC-25 JSON evidence outside the repository."""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath


MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


class ExternalWriteError(Exception):
    """Stable error code only."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class WriteResult:
    sha256: str
    byte_count: int


def _parts(path: Path) -> tuple[str, ...]:
    raw = str(path)
    pure = PurePath(raw)
    if not pure.is_absolute():
        raise ExternalWriteError("OUTPUT_PATH_NOT_ABSOLUTE")
    parts = tuple(pure.parts[1:])
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ExternalWriteError("OUTPUT_PATH_INVALID_COMPONENT")
    return parts


def _lexically_within(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(parent))) == str(parent)
    except ValueError:
        return False


def _require_platform() -> None:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise ExternalWriteError("OUTPUT_PLATFORM_UNSUPPORTED")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise ExternalWriteError("OUTPUT_PLATFORM_UNSUPPORTED")
    # CPython exposes replace() with rename()'s dir-fd implementation but does
    # not list the alias itself in supports_dir_fd on every supported platform.
    if os.rename not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd:
        raise ExternalWriteError("OUTPUT_PLATFORM_UNSUPPORTED")


def _open_dir_chain(path: Path) -> int:
    parts = _parts(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT") from exc
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException as _failure:
        os.close(fd)
        raise


def _open_relative_parent(root_fd: int, parts: tuple[str, ...]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT") from exc
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException as _failure:
        os.close(fd)
        raise


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ExternalWriteError("OUTPUT_WRITE_FAILED")
        view = view[written:]


def _same_inode(left_fd: int, right_fd: int) -> bool:
    left = os.fstat(left_fd)
    right = os.fstat(right_fd)
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _revalidate_chain(evidence_root: Path, root_fd: int, parent_parts: tuple[str, ...], parent_fd: int) -> None:
    """Detect renames/swaps of the named root or output parent."""
    check_root = _open_dir_chain(evidence_root)
    check_parent = -1
    try:
        if not _same_inode(root_fd, check_root):
            raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT")
        check_parent = _open_relative_parent(check_root, parent_parts)
        if not _same_inode(parent_fd, check_parent):
            raise ExternalWriteError("OUTPUT_PATH_SYMLINK_COMPONENT")
    finally:
        if check_parent >= 0:
            os.close(check_parent)
        os.close(check_root)


def _read_all(fd: int, expected_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, expected_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > expected_bytes:
            raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
    raw = b"".join(chunks)
    if len(raw) != expected_bytes:
        raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
    return raw


def read_external_regular(
    *, evidence_root: Path, path: Path, max_bytes: int
) -> bytes:
    """Read one external regular file without following path components."""
    _require_platform()
    root_parts = _parts(evidence_root)
    path_parts = _parts(path)
    if not _lexically_within(path, evidence_root):
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    relative = path_parts[len(root_parts):]
    if not relative or path_parts[:len(root_parts)] != root_parts:
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    root_fd = _open_dir_chain(evidence_root)
    parent_fd = -1
    try:
        parent_fd = _open_relative_parent(root_fd, relative[:-1])
        try:
            fd = os.open(relative[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE") from exc
        try:
            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > max_bytes:
                raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")
            raw = _read_all(fd, file_stat.st_size)
        finally:
            os.close(fd)
        return raw
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
        os.close(root_fd)


def write_external_json_atomic(
    *, repo_root: Path, evidence_root: Path, output: Path, payload: bytes
) -> WriteResult:
    _require_platform()
    repo_parts = _parts(repo_root)
    root_parts = _parts(evidence_root)
    output_parts = _parts(output)
    del repo_parts
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ExternalWriteError("OUTPUT_PAYLOAD_TOO_LARGE")
    if not _lexically_within(output, evidence_root):
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    if _lexically_within(output, repo_root) or _lexically_within(evidence_root, repo_root):
        raise ExternalWriteError("OUTPUT_PATH_INSIDE_REPOSITORY")
    relative = output_parts[len(root_parts):]
    if not relative or output_parts[:len(root_parts)] != root_parts:
        raise ExternalWriteError("OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT")
    parent_parts = relative[:-1]
    filename = relative[-1]

    root_fd = _open_dir_chain(evidence_root)
    parent_fd = -1
    temporary = f".{filename}.ac25-{secrets.token_hex(16)}.tmp"
    temporary_created = False
    try:
        parent_fd = _open_relative_parent(root_fd, parent_parts)
        try:
            existing = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE") from exc
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            temp_fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_WRITE_FAILED") from exc
        temporary_created = True
        try:
            _write_all(temp_fd, payload)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        _revalidate_chain(evidence_root, root_fd, parent_parts, parent_fd)
        os.replace(temporary, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary_created = False
        os.fsync(parent_fd)
        try:
            _revalidate_chain(evidence_root, root_fd, parent_parts, parent_fd)
        except ExternalWriteError:
            try:
                os.unlink(filename, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                pass
            raise

        try:
            final_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError as exc:
            raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH") from exc
        try:
            if not stat.S_ISREG(os.fstat(final_fd).st_mode):
                raise ExternalWriteError("OUTPUT_PATH_UNSAFE_TYPE")
            reopened = _read_all(final_fd, len(payload))
        finally:
            os.close(final_fd)
        if reopened != payload:
            raise ExternalWriteError("OUTPUT_REOPEN_MISMATCH")
        return WriteResult(hashlib.sha256(reopened).hexdigest(), len(reopened))
    finally:
        if temporary_created and parent_fd >= 0:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd >= 0:
            os.close(parent_fd)
        os.close(root_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    try:
        result = write_external_json_atomic(
            repo_root=Path(args.repo_root),
            evidence_root=Path(args.evidence_root),
            output=Path(args.output),
            payload=payload,
        )
    except ExternalWriteError as exc:
        print(f"ERROR_CODE={exc.code}")
        return 1
    print("EXTERNAL_JSON_WRITTEN=1")
    print(f"OUTPUT_SHA256={result.sha256}")
    print(f"OUTPUT_BYTES={result.byte_count}")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
