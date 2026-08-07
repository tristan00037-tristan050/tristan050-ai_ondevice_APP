"""Private immutable byte leases consumed by native Helper1 workers."""
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from typing import Any

from .contracts import canonical_json, sha256_bytes
from .security import Helper1SecurityError, VerifiedAssetClosure


@dataclass(frozen=True)
class AssetConsumptionReceipt:
    logical_path: str
    bytes_before: int
    sha256_before: str
    bytes_after: int
    sha256_after: str
    descriptor_only: bool = True
    schema_version: str = "butler.helper1.asset-consumption.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "logical_path": self.logical_path,
            "bytes_before": self.bytes_before,
            "sha256_before": self.sha256_before,
            "bytes_after": self.bytes_after,
            "sha256_after": self.sha256_after,
            "descriptor_only": self.descriptor_only,
        }

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()))


class VerifiedAssetLease:
    """Owns one unlinked, read-only inode copied from verified closure bytes."""

    def __init__(self, *, logical_path: str, fd: int, size: int, digest: str) -> None:
        self.logical_path = logical_path
        self._fd = fd
        self.size = size
        self.digest = digest
        self._closed = False

    @classmethod
    def create(cls, closure: VerifiedAssetClosure, logical_path: str) -> "VerifiedAssetLease":
        source_fd = closure.open_verified(logical_path)
        writable_fd = -1
        readonly_fd = -1
        stage_path: str | None = None
        try:
            writable_fd, stage_path = tempfile.mkstemp(prefix="butler-helper1-asset-")
            digest = hashlib.sha256()
            total = 0
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                view = memoryview(block)
                while view:
                    written = os.write(writable_fd, view)
                    if written <= 0:
                        raise Helper1SecurityError("ASSET_LEASE_WRITE_FAILED")
                    view = view[written:]
                digest.update(block)
                total += len(block)
            os.fsync(writable_fd)
            observed = digest.hexdigest()
            record = closure.files.get(logical_path)
            if record is None or total != record.bytes or observed != record.sha256:
                raise Helper1SecurityError("ASSET_LEASE_DIGEST_MISMATCH")
            os.fchmod(writable_fd, 0o400)
            os.close(writable_fd)
            writable_fd = -1
            readonly_fd = os.open(
                stage_path,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            os.unlink(stage_path)
            stage_path = None
            info = os.fstat(readonly_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != total:
                raise Helper1SecurityError("ASSET_LEASE_IDENTITY_INVALID")
            lease = cls(
                logical_path=logical_path,
                fd=readonly_fd,
                size=total,
                digest=observed,
            )
            readonly_fd = -1
            return lease
        finally:
            os.close(source_fd)
            if writable_fd >= 0:
                os.close(writable_fd)
            if readonly_fd >= 0:
                os.close(readonly_fd)
            if stage_path is not None:
                try:
                    os.unlink(stage_path)
                except FileNotFoundError:
                    pass

    def duplicate_fd(self) -> int:
        if self._closed:
            raise Helper1SecurityError("ASSET_LEASE_CLOSED")
        duplicate = os.dup(self._fd)
        os.lseek(duplicate, 0, os.SEEK_SET)
        return duplicate

    def measure(self) -> tuple[int, str]:
        duplicate = self.duplicate_fd()
        try:
            digest = hashlib.sha256()
            total = 0
            while True:
                block = os.read(duplicate, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                total += len(block)
        finally:
            os.close(duplicate)
        observed = digest.hexdigest()
        if total != self.size or observed != self.digest:
            raise Helper1SecurityError("ASSET_LEASE_CHANGED")
        return total, observed

    def consumption_receipt(
        self, before: tuple[int, str], after: tuple[int, str]
    ) -> AssetConsumptionReceipt:
        if before != after or before != (self.size, self.digest):
            raise Helper1SecurityError("ASSET_CONSUMPTION_MISMATCH")
        return AssetConsumptionReceipt(
            logical_path=self.logical_path,
            bytes_before=before[0],
            sha256_before=before[1],
            bytes_after=after[0],
            sha256_after=after[1],
        )

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

    def __enter__(self) -> "VerifiedAssetLease":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
