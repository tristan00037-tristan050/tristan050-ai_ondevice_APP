from __future__ import annotations

import hashlib
import os
import secrets
import stat
from pathlib import Path

from .contracts import AssetEntry, FileIdentity, VerifiedAsset
from .errors import AssetError, block
from .formats import validate_format
from .path_policy import validate_relative_path

HASH_CHUNK_BYTES = 8 * 1024 * 1024
_OPEN_BASE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW_ANY", getattr(os, "O_NOFOLLOW", 0))
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


class SafeRoot:
    """Descriptor-rooted, no-follow traversal for a verified asset root."""

    def __init__(self, root: Path) -> None:
        if os.name == "nt":
            # Python dir_fd traversal cannot provide the required Windows
            # reparse-point/ADS guarantees. The native handle bridge must be
            # used before Windows is declared supported.
            raise block("PLATFORM_UNSUPPORTED")
        try:
            info = root.lstat()
            if root.is_symlink() or not stat.S_ISDIR(info.st_mode):
                raise block("SYMLINK_REJECTED")
            self._fd = os.open(root, _OPEN_BASE_FLAGS | _DIRECTORY | _NOFOLLOW)
            self._identity = FileIdentity.from_stat(os.fstat(self._fd))
        except AssetError:
            raise
        except OSError as exc:
            raise block("VERIFY_IO_ERROR") from exc

    @property
    def identity(self) -> FileIdentity:
        return self._identity

    def open_regular(self, relative_path: str) -> int:
        parts = validate_relative_path(relative_path).split("/")
        current = os.dup(self._fd)
        try:
            for part in parts[:-1]:
                following = os.open(
                    part,
                    _OPEN_BASE_FLAGS | _DIRECTORY | _NOFOLLOW,
                    dir_fd=current,
                )
                os.close(current)
                current = following
            result = os.open(parts[-1], _OPEN_BASE_FLAGS | _NOFOLLOW, dir_fd=current)
            info = os.fstat(result)
            if not stat.S_ISREG(info.st_mode):
                os.close(result)
                raise block("NOT_REGULAR_FILE")
            return result
        except AssetError:
            raise
        except OSError as exc:
            raise block("SYMLINK_REJECTED") from exc
        finally:
            os.close(current)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "SafeRoot":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _full_sha256(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, HASH_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def verify_entry(root: SafeRoot, entry: AssetEntry) -> VerifiedAsset:
    fd = root.open_regular(entry.relative_path)
    try:
        before = FileIdentity.from_stat(os.fstat(fd))
        if before.link_count != 1:
            raise block("HARDLINK_REJECTED")
        if before.mode & 0o111:
            raise block("UNSAFE_SERIALIZATION")
        if before.size != entry.size_bytes:
            raise block("FILE_SIZE_MISMATCH")
        digest = _full_sha256(fd)
        if not secrets.compare_digest(digest, entry.sha256):
            raise block("FILE_DIGEST_MISMATCH")
        duplicate = os.dup(fd)
        try:
            with os.fdopen(duplicate, "rb", closefd=True) as handle:
                validate_format(handle, entry)
        except Exception:
            try:
                os.close(duplicate)
            except OSError:
                pass
            raise
        after = FileIdentity.from_stat(os.fstat(fd))
        if before != after:
            raise block("TOCTOU_CHANGED")
        identity_basis = (
            f"{before.device}:{before.inode}:{before.size}:"
            f"{before.mtime_ns}:{before.ctime_ns}:{entry.sha256}"
        )
        return VerifiedAsset(
            entry=entry,
            fd=fd,
            identity=before,
            identity_token=hashlib.sha256(identity_basis.encode("ascii")).hexdigest(),
        )
    except Exception:
        os.close(fd)
        raise
