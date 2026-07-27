from __future__ import annotations

import fcntl
import hashlib
import os
import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import AssetError, block

COPY_CHUNK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class SnapshotResult:
    fd: int
    digest: str
    size: int
    seal_type: str


def _copy(source_fd: int, destination_fd: int, expected_size: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(source_fd, 0, os.SEEK_SET)
    os.lseek(destination_fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(source_fd, COPY_CHUNK_BYTES)
        if not chunk:
            break
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            if written <= 0:
                raise block("BLOCK_SNAPSHOT_COPY_FAILED")
            view = view[written:]
        digest.update(chunk)
        total += len(chunk)
        if total > expected_size:
            raise block("BLOCK_SOURCE_CHANGED")
    if total != expected_size:
        raise block("BLOCK_SOURCE_CHANGED")
    os.fsync(destination_fd)
    return total, digest.hexdigest()


def _linux_snapshot(source_fd: int, expected_size: int) -> SnapshotResult:
    if not hasattr(os, "memfd_create"):
        raise block("BLOCK_PLATFORM_UNSUPPORTED")
    flags = getattr(os, "MFD_CLOEXEC", 0x0001) | getattr(
        os, "MFD_ALLOW_SEALING", 0x0002
    )
    fd = os.memfd_create("butler-asset", flags)
    try:
        size, digest = _copy(source_fd, fd, expected_size)
        seals = (
            getattr(fcntl, "F_SEAL_WRITE", 0x0008)
            | getattr(fcntl, "F_SEAL_GROW", 0x0004)
            | getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
            | getattr(fcntl, "F_SEAL_SEAL", 0x0001)
        )
        fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), seals)
        actual = fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034))
        if actual & seals != seals:
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        os.lseek(fd, 0, os.SEEK_SET)
        return SnapshotResult(fd, digest, size, "linux_memfd")
    except Exception:
        os.close(fd)
        raise


def _darwin_snapshot(
    source_fd: int, expected_size: int, authority_root: Path | None
) -> SnapshotResult:
    if authority_root is None:
        authority_root = Path(tempfile.gettempdir()) / "butler-asset-authority"
    root = authority_root / "asset-snapshots"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    write_fd, name = tempfile.mkstemp(prefix=".snapshot-", dir=root)
    readonly_fd = -1
    try:
        os.fchmod(write_fd, 0o400)
        size, digest = _copy(source_fd, write_fd, expected_size)
        before = os.fstat(write_fd)
        readonly_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        after = os.fstat(readonly_fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        os.unlink(name)
        os.close(write_fd)
        write_fd = -1
        os.lseek(readonly_fd, 0, os.SEEK_SET)
        return SnapshotResult(
            readonly_fd, digest, size, "macos_authority_store"
        )
    except Exception:
        if readonly_fd >= 0:
            os.close(readonly_fd)
        raise
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        try:
            os.unlink(name)
        except OSError:
            pass


def create_sealed_snapshot(
    source_fd: int,
    *,
    expected_size: int,
    authority_root: Path | None,
) -> SnapshotResult:
    system = platform.system()
    if system == "Linux":
        return _linux_snapshot(source_fd, expected_size)
    if system == "Darwin":
        return _darwin_snapshot(source_fd, expected_size, authority_root)
    if system == "Windows":
        raise block("BLOCK_PLATFORM_UNSUPPORTED")
    raise block("BLOCK_PLATFORM_UNSUPPORTED")


def digest_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, COPY_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()
