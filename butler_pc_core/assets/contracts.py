from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from typing import BinaryIO, Mapping

from .snapshot import open_read_view


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


class LeaseState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    SOURCE_OPENED = "SOURCE_OPENED"
    SNAPSHOT_COPYING = "SNAPSHOT_COPYING"
    SNAPSHOT_VERIFIED = "SNAPSHOT_VERIFIED"
    SNAPSHOT_SEALED = "SNAPSHOT_SEALED"
    LEASE_ACTIVE = "LEASE_ACTIVE"
    LEASE_CLOSED = "LEASE_CLOSED"
    BLOCKED = "BLOCKED"


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


@dataclass(frozen=True)
class AssetIdentity:
    role: str
    sha256: str
    size_bytes: int
    format: str
    manifest_set_sha256: str


class NativeReadHandle:
    """Owned descriptor for the already-verified immutable loader object."""

    __slots__ = ("_fd", "identity", "seal_type")

    def __init__(
        self,
        fd: int,
        *,
        identity: AssetIdentity,
        seal_type: str,
    ) -> None:
        if fd < 0:
            raise ValueError("NATIVE_HANDLE_INVALID")
        self._fd = fd
        self.identity = identity
        self.seal_type = seal_type

    @property
    def fd(self) -> int:
        if self._fd < 0:
            raise RuntimeError("NATIVE_HANDLE_CLOSED")
        return self._fd

    def duplicate(self) -> "NativeReadHandle":
        duplicate = os.dup(self.fd)
        if self.seal_type != "darwin_posix_shm_readonly":
            os.lseek(duplicate, 0, os.SEEK_SET)
        return NativeReadHandle(
            duplicate,
            identity=self.identity,
            seal_type=self.seal_type,
        )

    def open(self) -> BinaryIO:
        return open_read_view(
            self.fd,
            size=self.identity.size_bytes,
            seal_type=self.seal_type,
        )

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "NativeReadHandle":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass


@dataclass(frozen=True)
class LoadedModelReceipt:
    schema_version: int
    run_id: str
    nonce: str
    asset_role: str
    asset_sha256: str
    mapped_asset_sha256: str
    mapped_length: int
    loader_binary_sha256: str
    native_backend_sha256: str
    platform_seal: str
    result: str
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "nonce": self.nonce,
            "asset_role": self.asset_role,
            "asset_sha256": self.asset_sha256,
            "mapped_asset_sha256": self.mapped_asset_sha256,
            "mapped_length": self.mapped_length,
            "loader_binary_sha256": self.loader_binary_sha256,
            "native_backend_sha256": self.native_backend_sha256,
            "platform_seal": self.platform_seal,
            "result": self.result,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class VerifiedAssetReceipt:
    schema_version: int
    run_id: str
    request_id: str
    nonce: str
    role: str
    purpose: str
    manifest_set_digest: str
    asset_digest: str
    snapshot_digest: str
    loader_input_digest: str
    source_oid: Mapping[str, str]
    source_tree_oid: Mapping[str, str]
    trust_policy_digest: str
    signer_key_id: str
    platform_seal_type: str
    ordered_trace_digest: str
    result: str
    reason_code: str | None
    issued_monotonic_ns: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "nonce": self.nonce,
            "role": self.role,
            "purpose": self.purpose,
            "manifest_set_digest": self.manifest_set_digest,
            "asset_digest": self.asset_digest,
            "snapshot_digest": self.snapshot_digest,
            "loader_input_digest": self.loader_input_digest,
            "source_oid": dict(self.source_oid),
            "source_tree_oid": dict(self.source_tree_oid),
            "trust_policy_digest": self.trust_policy_digest,
            "signer_key_id": self.signer_key_id,
            "platform_seal_type": self.platform_seal_type,
            "ordered_trace_digest": self.ordered_trace_digest,
            "result": self.result,
            "reason_code": self.reason_code,
        }


class VerifiedAsset:
    """An owned immutable snapshot descriptor; the source fd never escapes."""

    __slots__ = (
        "entry",
        "_fd",
        "identity",
        "identity_token",
        "snapshot_digest",
        "seal_type",
    )

    def __init__(
        self,
        *,
        entry: AssetEntry,
        fd: int,
        identity: FileIdentity,
        identity_token: str,
        snapshot_digest: str,
        seal_type: str,
    ) -> None:
        self.entry = entry
        self._fd = fd
        self.identity = identity
        self.identity_token = identity_token
        self.snapshot_digest = snapshot_digest
        self.seal_type = seal_type

    def open(self) -> BinaryIO:
        return open_read_view(
            self._fd,
            size=self.entry.size_bytes,
            seal_type=self.seal_type,
        )

    def duplicate_read_handle(self, *, manifest_set_sha256: str) -> NativeReadHandle:
        if self._fd < 0:
            raise RuntimeError("LEASE_NOT_ACTIVE")
        duplicate = os.dup(self._fd)
        if self.seal_type != "darwin_posix_shm_readonly":
            os.lseek(duplicate, 0, os.SEEK_SET)
        return NativeReadHandle(
            duplicate,
            identity=AssetIdentity(
                role=self.entry.role,
                sha256=self.snapshot_digest,
                size_bytes=self.entry.size_bytes,
                format=self.entry.validator,
                manifest_set_sha256=manifest_set_sha256,
            ),
            seal_type=self.seal_type,
        )

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
    __slots__ = (
        "capability",
        "asset_group",
        "group_version",
        "request_id",
        "purpose",
        "_assets",
        "_state",
        "_receipts",
    )

    def __init__(
        self,
        *,
        capability: str,
        asset_group: str,
        group_version: int,
        assets: Mapping[str, VerifiedAsset],
        request_id: str = "legacy-request",
        purpose: str = "legacy-loader",
        run_id: str = "legacy-run",
        manifest_set_digest: str = "",
        source_oid: Mapping[str, str] | None = None,
        source_tree_oid: Mapping[str, str] | None = None,
        trust_policy_digest: str = "",
        signer_key_id: str = "",
    ) -> None:
        self.capability = capability
        self.asset_group = asset_group
        self.group_version = group_version
        self.request_id = request_id
        self.purpose = purpose
        self._assets = dict(assets)
        self._state = LeaseState.LEASE_ACTIVE
        trace = (
            "SOURCE_OPENED",
            "SNAPSHOT_COPYING",
            "SNAPSHOT_VERIFIED",
            "SNAPSHOT_SEALED",
            "LEASE_ACTIVE",
        )
        trace_digest = hashlib.sha256(
            json.dumps(trace, separators=(",", ":")).encode("ascii")
        ).hexdigest()
        self._receipts = {
            role: VerifiedAssetReceipt(
                schema_version=1,
                run_id=run_id,
                request_id=request_id,
                nonce=secrets.token_hex(16),
                role=role,
                purpose=purpose,
                manifest_set_digest=manifest_set_digest,
                asset_digest=asset.entry.sha256,
                snapshot_digest=asset.snapshot_digest,
                loader_input_digest=asset.snapshot_digest,
                source_oid=dict(source_oid or {}),
                source_tree_oid=dict(source_tree_oid or {}),
                trust_policy_digest=trust_policy_digest,
                signer_key_id=signer_key_id,
                platform_seal_type=asset.seal_type,
                ordered_trace_digest=trace_digest,
                result="ALLOW",
                reason_code="OK",
                issued_monotonic_ns=time.monotonic_ns(),
            )
            for role, asset in self._assets.items()
        }

    @property
    def state(self) -> LeaseState:
        return self._state

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))

    def require(self, role: str) -> VerifiedAsset:
        if self._state is not LeaseState.LEASE_ACTIVE:
            raise RuntimeError("LEASE_NOT_ACTIVE")
        return self._assets[role]

    def receipt(self, role: str) -> VerifiedAssetReceipt:
        if self._state is not LeaseState.LEASE_ACTIVE:
            raise RuntimeError("LEASE_NOT_ACTIVE")
        return self._receipts[role]

    def close(self) -> None:
        if self._state is LeaseState.LEASE_CLOSED:
            return
        assets, self._assets = self._assets, {}
        for asset in assets.values():
            asset.close()
        self._state = LeaseState.LEASE_CLOSED

    def __enter__(self) -> "CapabilityLease":
        return self

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
