from __future__ import annotations

import json
import os
import re
import struct
import stat
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

from .contracts import ReleaseProfile
from .errors import AssetError, block

MAX_BOOTSTRAP_BYTES = 16 * 1024
_OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_LOCK = threading.Lock()
_CONTEXT: "PlatformAssetContext | None" = None


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise block("PLATFORM_CONTEXT_INVALID")
        result[key] = value
    return result


@dataclass(frozen=True)
class PlatformAssetContext:
    resource_root: Path | None
    app_data_root: Path
    release_profile: ReleaseProfile
    build_id: str
    source_commit: str
    source_tree: str
    manifest_set_sha256: str | None
    native_authority: bool
    asset_root_fd: int | None = None
    trust_root_status: str = "TRUST_ROOT_NOT_CONFIGURED"
    root_policy_sha256: str | None = None
    trusted_keys: tuple[dict[str, object], ...] = ()
    trust_epoch: int | None = None
    revoked_key_ids: tuple[str, ...] = ()
    bootstrap_security_state: dict[str, object] | None = None


def _absolute_directory(value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise block("PLATFORM_CONTEXT_INVALID")
    path = Path(value)
    if not path.is_absolute():
        raise block("PLATFORM_CONTEXT_INVALID")
    try:
        info = path.lstat()
    except OSError as exc:
        raise block("PLATFORM_CONTEXT_INVALID") from exc
    if path.is_symlink() or not path.is_dir() or info.st_nlink < 1:
        raise block("PLATFORM_CONTEXT_INVALID")
    return path


def parse_platform_context(raw: bytes, *, native_authority: bool) -> PlatformAssetContext:
    if not raw or len(raw) > MAX_BOOTSTRAP_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise block("PLATFORM_CONTEXT_INVALID")
    try:
        text = raw.decode("utf-8")
        if text != unicodedata.normalize("NFC", text):
            raise block("PLATFORM_CONTEXT_INVALID")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                block("PLATFORM_CONTEXT_INVALID")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, AssetError) as exc:
        raise block("PLATFORM_CONTEXT_INVALID") from exc
    required = {
        "schema_version",
        "app_data_root",
        "release_profile",
        "build_id",
        "source_commit",
        "source_tree",
        "manifest_set_sha256",
    }
    optional = {
        "resource_root",
        "asset_root_fd",
        "trust_root_status",
        "root_policy_sha256",
        "trusted_keys",
        "trust_epoch",
        "revoked_key_ids",
        "security_state",
    }
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or not set(value) <= required | optional
        or ("resource_root" in value) == ("asset_root_fd" in value)
    ):
        raise block("PLATFORM_CONTEXT_INVALID")
    if value["schema_version"] != 1:
        raise block("PLATFORM_CONTEXT_INVALID")
    try:
        profile = ReleaseProfile(value["release_profile"])
    except (TypeError, ValueError) as exc:
        raise block("PLATFORM_CONTEXT_INVALID") from exc
    build_id = value["build_id"]
    commit = value["source_commit"]
    tree = value["source_tree"]
    manifest_set = value["manifest_set_sha256"]
    trust_status = value.get("trust_root_status", "TRUST_ROOT_NOT_CONFIGURED")
    root_policy = value.get("root_policy_sha256")
    trusted_keys = value.get("trusted_keys", [])
    trust_epoch = value.get("trust_epoch")
    revoked = value.get("revoked_key_ids", [])
    security_state = value.get("security_state")
    if (
        not isinstance(build_id, str)
        or not 1 <= len(build_id) <= 128
        or not isinstance(commit, str)
        or not _OID_RE.fullmatch(commit)
        or not isinstance(tree, str)
        or not _OID_RE.fullmatch(tree)
        or (manifest_set is not None and (not isinstance(manifest_set, str) or not _SHA_RE.fullmatch(manifest_set)))
        or trust_status
        not in {"TRUST_ROOT_NOT_CONFIGURED", "TRUST_ROOT_CONFIGURED"}
        or (root_policy is not None and (not isinstance(root_policy, str) or not _SHA_RE.fullmatch(root_policy)))
        or not isinstance(trusted_keys, list)
        or not isinstance(revoked, list)
        or any(not isinstance(item, dict) for item in trusted_keys)
        or any(not isinstance(item, str) or not item for item in revoked)
        or (security_state is not None and not isinstance(security_state, dict))
        or (trust_epoch is not None and (not isinstance(trust_epoch, int) or isinstance(trust_epoch, bool) or trust_epoch <= 0))
    ):
        raise block("PLATFORM_CONTEXT_INVALID")
    if commit in {"0" * len(commit), "f" * len(commit)} or tree in {
        "0" * len(tree),
        "f" * len(tree),
    }:
        raise block("PLATFORM_CONTEXT_INVALID")
    if profile is ReleaseProfile.PRODUCTION and not native_authority:
        raise block("OVERRIDE_FORBIDDEN")
    resource_root = (
        _absolute_directory(value["resource_root"])
        if "resource_root" in value
        else None
    )
    asset_root_fd = value.get("asset_root_fd")
    if asset_root_fd is not None:
        if (
            not isinstance(asset_root_fd, int)
            or isinstance(asset_root_fd, bool)
            or asset_root_fd < 0
        ):
            raise block("PLATFORM_CONTEXT_INVALID")
        try:
            if not stat.S_ISDIR(os.fstat(asset_root_fd).st_mode):
                raise block("PLATFORM_CONTEXT_INVALID")
        except OSError as exc:
            raise block("PLATFORM_CONTEXT_INVALID") from exc
    if trust_status == "TRUST_ROOT_CONFIGURED" and (
        root_policy is None or not trusted_keys or trust_epoch is None
    ):
        raise block("BLOCK_ROOT_POLICY_UNPINNED")
    return PlatformAssetContext(
        resource_root=resource_root,
        app_data_root=_absolute_directory(value["app_data_root"]),
        release_profile=profile,
        build_id=build_id,
        source_commit=commit,
        source_tree=tree,
        manifest_set_sha256=manifest_set,
        native_authority=native_authority,
        asset_root_fd=asset_root_fd,
        trust_root_status=trust_status,
        root_policy_sha256=root_policy,
        trusted_keys=tuple(trusted_keys),
        trust_epoch=trust_epoch,
        revoked_key_ids=tuple(revoked),
        bootstrap_security_state=security_state,
    )


def install_platform_context(context: PlatformAssetContext) -> None:
    global _CONTEXT
    with _LOCK:
        if _CONTEXT is not None and _CONTEXT != context:
            raise block("PLATFORM_CONTEXT_ALREADY_SET")
        _CONTEXT = context


def _read_native_bootstrap_binary(stream: BinaryIO) -> PlatformAssetContext:
    header = stream.read(4)
    if len(header) != 4:
        raise block("PLATFORM_CONTEXT_INVALID")
    (frame_size,) = struct.unpack(">I", header)
    if not 1 <= frame_size <= MAX_BOOTSTRAP_BYTES:
        raise block("PLATFORM_CONTEXT_INVALID")
    raw = stream.read(frame_size)
    if len(raw) != frame_size:
        raise block("PLATFORM_CONTEXT_INVALID")
    context = parse_platform_context(raw, native_authority=True)
    install_platform_context(context)
    return context


def read_native_bootstrap(stream: TextIO) -> PlatformAssetContext:
    return _read_native_bootstrap_binary(stream.buffer)


def read_native_bootstrap_fd(fd: int) -> PlatformAssetContext:
    if not isinstance(fd, int) or isinstance(fd, bool) or fd < 0:
        raise block("PLATFORM_CONTEXT_INVALID")
    with os.fdopen(fd, "rb", closefd=True) as stream:
        return _read_native_bootstrap_binary(stream)


def get_platform_context() -> PlatformAssetContext:
    with _LOCK:
        context = _CONTEXT
    if context is None:
        raise block("PLATFORM_CONTEXT_MISSING")
    return context
