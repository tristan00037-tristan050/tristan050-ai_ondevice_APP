from __future__ import annotations

import json
import os
import re
import struct
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

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
    resource_root: Path
    app_data_root: Path
    release_profile: ReleaseProfile
    build_id: str
    source_commit: str
    source_tree: str
    manifest_set_sha256: str | None
    native_authority: bool


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
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "resource_root",
        "app_data_root",
        "release_profile",
        "build_id",
        "source_commit",
        "source_tree",
        "manifest_set_sha256",
    }:
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
    if (
        not isinstance(build_id, str)
        or not 1 <= len(build_id) <= 128
        or not isinstance(commit, str)
        or not _OID_RE.fullmatch(commit)
        or not isinstance(tree, str)
        or not _OID_RE.fullmatch(tree)
        or (manifest_set is not None and (not isinstance(manifest_set, str) or not _SHA_RE.fullmatch(manifest_set)))
    ):
        raise block("PLATFORM_CONTEXT_INVALID")
    if profile is ReleaseProfile.PRODUCTION and not native_authority:
        raise block("OVERRIDE_FORBIDDEN")
    return PlatformAssetContext(
        resource_root=_absolute_directory(value["resource_root"]),
        app_data_root=_absolute_directory(value["app_data_root"]),
        release_profile=profile,
        build_id=build_id,
        source_commit=commit,
        source_tree=tree,
        manifest_set_sha256=manifest_set,
        native_authority=native_authority,
    )


def install_platform_context(context: PlatformAssetContext) -> None:
    global _CONTEXT
    with _LOCK:
        if _CONTEXT is not None and _CONTEXT != context:
            raise block("PLATFORM_CONTEXT_ALREADY_SET")
        _CONTEXT = context


def read_native_bootstrap(stream: TextIO) -> PlatformAssetContext:
    header = stream.buffer.read(4)
    if len(header) != 4:
        raise block("PLATFORM_CONTEXT_INVALID")
    (frame_size,) = struct.unpack(">I", header)
    if not 1 <= frame_size <= MAX_BOOTSTRAP_BYTES:
        raise block("PLATFORM_CONTEXT_INVALID")
    raw = stream.buffer.read(frame_size)
    if len(raw) != frame_size:
        raise block("PLATFORM_CONTEXT_INVALID")
    context = parse_platform_context(raw, native_authority=True)
    install_platform_context(context)
    return context


def get_platform_context() -> PlatformAssetContext:
    with _LOCK:
        context = _CONTEXT
    if context is None:
        raise block("PLATFORM_CONTEXT_MISSING")
    return context


def install_test_context(
    *,
    resource_root: Path,
    app_data_root: Path,
    manifest_set_sha256: str | None,
) -> PlatformAssetContext:
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        raise block("OVERRIDE_FORBIDDEN")
    context = PlatformAssetContext(
        resource_root=resource_root,
        app_data_root=app_data_root,
        release_profile=ReleaseProfile.TEST,
        build_id="test-build",
        source_commit="0" * 40,
        source_tree="0" * 40,
        manifest_set_sha256=manifest_set_sha256,
        native_authority=False,
    )
    install_platform_context(context)
    return context
