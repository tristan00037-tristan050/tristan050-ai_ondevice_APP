from __future__ import annotations

import fcntl
import hashlib
import io
import mmap
import os
import platform
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

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
        raise block("BLOCK_SNAPSHOT_CREATE_FAILED")
    root_fd = -1
    object_root_fd = -1
    write_fd = -1
    readonly_fd = -1
    object_name = f".asset-{secrets.token_hex(24)}"
    try:
        root_fd = os.open(
            authority_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.mkdir(".asset-objects", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        object_root_fd = os.open(
            ".asset-objects",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd,
        )
        root_info = os.fstat(object_root_fd)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != os.getuid()
            or stat.S_IMODE(root_info.st_mode) != 0o700
        ):
            raise block("BLOCK_SNAPSHOT_CREATE_FAILED")
        write_fd = os.open(
            object_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=object_root_fd,
        )
        created = os.fstat(write_fd)
        if (
            not stat.S_ISREG(created.st_mode)
            or created.st_uid != os.getuid()
            or created.st_nlink != 1
            or stat.S_IMODE(created.st_mode) != 0o600
        ):
            raise block("BLOCK_SNAPSHOT_CREATE_FAILED")
        readonly_fd = os.open(
            object_name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=object_root_fd,
        )
        opened = os.fstat(readonly_fd)
        if (
            created.st_dev,
            created.st_ino,
            created.st_nlink,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_nlink,
        ):
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        # Remove the namespace entry before the first asset byte is copied.
        # The verified object is therefore never available through a path.
        os.unlink(object_name, dir_fd=object_root_fd)
        if os.fstat(write_fd).st_nlink != 0:
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        size, digest = _copy(source_fd, write_fd, expected_size)
        before = os.fstat(write_fd)
        after = os.fstat(readonly_fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_nlink,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_nlink,
        ):
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        os.close(write_fd)
        write_fd = -1
        try:
            os.write(readonly_fd, b"x")
        except OSError:
            pass
        else:
            raise block("BLOCK_SNAPSHOT_SEAL_FAILED")
        os.lseek(readonly_fd, 0, os.SEEK_SET)
        return SnapshotResult(readonly_fd, digest, size, "macos_native_mapping")
    except Exception:
        if readonly_fd >= 0:
            os.close(readonly_fd)
        raise
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        if object_root_fd >= 0:
            try:
                os.unlink(object_name, dir_fd=object_root_fd)
            except OSError:
                pass
            os.close(object_root_fd)
        if root_fd >= 0:
            os.close(root_fd)


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


def open_read_view(fd: int, *, size: int, seal_type: str) -> BinaryIO:
    if seal_type == "darwin_posix_shm_readonly":
        if size == 0:
            return io.BytesIO()
        return mmap.mmap(fd, size, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ)
    duplicate = os.dup(fd)
    os.lseek(duplicate, 0, os.SEEK_SET)
    return os.fdopen(duplicate, "rb", closefd=True)


def digest_fd(fd: int, *, size: int, seal_type: str) -> str:
    digest = hashlib.sha256()
    with open_read_view(fd, size=size, seal_type=seal_type) as stream:
        while True:
            chunk = stream.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
