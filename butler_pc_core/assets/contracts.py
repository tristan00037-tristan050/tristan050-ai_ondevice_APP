from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Mapping


class ReleaseProfile(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


class GroupState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_REQUIRED = "NOT_REQUIRED"
    VERIFYING = "VERIFYING"


@dataclass(frozen=True)
class AssetEntry:
    role: str
    relative_path: str
    size_bytes: int
    sha256: str
    media_type: str
    validator: str
    allow_empty: bool = False
    model_identity: Mapping[str, str] | None = None


@dataclass(frozen=True)
class AssetManifest:
    asset_group: str
    group_version: int
    required_for_profiles: tuple[str, ...]
    entries: tuple[AssetEntry, ...]
    digest: str


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    mode: int
    link_count: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> "FileIdentity":
        return cls(
            device=int(value.st_dev),
            inode=int(value.st_ino),
            size=int(value.st_size),
            mtime_ns=int(value.st_mtime_ns),
            ctime_ns=int(value.st_ctime_ns),
            mode=int(value.st_mode),
            link_count=int(value.st_nlink),
        )


class VerifiedAsset:
    """An owned verified descriptor. No filesystem path crosses this boundary."""

    __slots__ = ("entry", "_fd", "identity", "identity_token")

    def __init__(
        self,
        *,
        entry: AssetEntry,
        fd: int,
        identity: FileIdentity,
        identity_token: str,
    ) -> None:
        self.entry = entry
        self._fd = fd
        self.identity = identity
        self.identity_token = identity_token

    def open(self) -> BinaryIO:
        duplicate = os.dup(self._fd)
        os.lseek(duplicate, 0, os.SEEK_SET)
        return os.fdopen(duplicate, "rb", closefd=True)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass


class CapabilityLease:
    __slots__ = ("capability", "asset_group", "group_version", "_assets")

    def __init__(
        self,
        *,
        capability: str,
        asset_group: str,
        group_version: int,
        assets: Mapping[str, VerifiedAsset],
    ) -> None:
        self.capability = capability
        self.asset_group = asset_group
        self.group_version = group_version
        self._assets = dict(assets)

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))

    def require(self, role: str) -> VerifiedAsset:
        return self._assets[role]

    def materialize_directory(self) -> "MaterializedCapability":
        temporary = Path(tempfile.mkdtemp(prefix="butler-verified-assets-"))
        try:
            temporary.chmod(0o700)
            for asset in self._assets.values():
                relative = Path(asset.entry.relative_path)
                target = temporary.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                    0o400,
                )
                try:
                    with asset.open() as source, os.fdopen(
                        descriptor, "wb", closefd=True
                    ) as destination:
                        descriptor = -1
                        shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
                        destination.flush()
                        os.fsync(destination.fileno())
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
            for directory in sorted(
                (item for item in temporary.rglob("*") if item.is_dir()),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                directory.chmod(0o500)
            temporary.chmod(0o500)
            return MaterializedCapability(temporary)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def close(self) -> None:
        assets, self._assets = self._assets, {}
        for asset in assets.values():
            asset.close()

    def __enter__(self) -> "CapabilityLease":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class MaterializedCapability:
    __slots__ = ("root",)

    def __init__(self, root: Path) -> None:
        self.root = root

    def close(self) -> None:
        if self.root.exists():
            for item in self.root.rglob("*"):
                try:
                    item.chmod(0o700 if item.is_dir() else 0o600)
                except OSError:
                    pass
            try:
                self.root.chmod(0o700)
            except OSError:
                pass
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> Path:
        return self.root

    def __exit__(self, *_args: object) -> None:
        self.close()


@dataclass(frozen=True)
class GroupStatus:
    asset_group: str
    group_version: int
    state: GroupState
    reason: str | None = None


@dataclass(frozen=True)
class VerificationReceipt:
    schema_version: int
    run_id: str
    build_id: str
    release_profile: str
    asset_group: str
    group_version: int
    manifest_digest: str
    manifest_set_sha256: str
    roles: tuple[str, ...]
    identity_tokens: tuple[str, ...]
    verifier_version: str
    verified_monotonic_ns: int
