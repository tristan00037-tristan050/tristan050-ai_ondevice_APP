from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .contracts import AssetEntry, AssetManifest
from .errors import AssetError, block
from .path_policy import validate_relative_path

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_ENTRIES = 10_000
MAX_PROFILE_COUNT = 8
_NAME_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_ROLE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_MEDIA_TYPES = {
    "application/gguf",
    "application/json",
    "application/jsonl",
    "application/x-npy",
    "application/x-npz",
    "application/safetensors",
    "application/octet-stream",
    "text/plain",
}
_PROFILES = {"production", "development", "test"}
_TOP_KEYS = {
    "schema_version",
    "asset_group",
    "group_version",
    "required_for_profiles",
    "entries",
}
_ENTRY_REQUIRED = {
    "role",
    "relative_path",
    "size_bytes",
    "sha256",
    "media_type",
    "validator",
}
_ENTRY_KEYS = _ENTRY_REQUIRED | {"allow_empty", "model_identity"}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise block("MANIFEST_SCHEMA_INVALID")
        result[key] = value
    return result


def _load_json(raw: bytes) -> object:
    if not raw or len(raw) > MAX_MANIFEST_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise block("MANIFEST_SCHEMA_INVALID")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise block("MANIFEST_SCHEMA_INVALID") from exc
    if text != unicodedata.normalize("NFC", text):
        raise block("MANIFEST_SCHEMA_INVALID")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(block("MANIFEST_SCHEMA_INVALID")),
        )
    except (json.JSONDecodeError, AssetError) as exc:
        raise block("MANIFEST_SCHEMA_INVALID") from exc
    return value


def _model_identity(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise block("MANIFEST_SCHEMA_INVALID")
    allowed = {
        "model_id",
        "version",
        "architecture",
        "quantization",
        "base_model_sha256",
        "tokenizer_id",
    }
    if not {"model_id", "version", "architecture"} <= set(value) or not set(value) <= allowed:
        raise block("MANIFEST_SCHEMA_INVALID")
    if (
        not isinstance(value["model_id"], str)
        or not _MODEL_ID_RE.fullmatch(value["model_id"])
        or not all(
            isinstance(value[name], str) and 1 <= len(value[name]) <= 64
            for name in ("version", "architecture")
        )
        or (
            "quantization" in value
            and (
                not isinstance(value["quantization"], str)
                or not 1 <= len(value["quantization"]) <= 64
            )
        )
        or (
            "tokenizer_id" in value
            and (
                not isinstance(value["tokenizer_id"], str)
                or not 1 <= len(value["tokenizer_id"]) <= 128
            )
        )
    ):
        raise block("MANIFEST_SCHEMA_INVALID")
    base_sha = value.get("base_model_sha256")
    if base_sha is not None and not _SHA_RE.fullmatch(base_sha):
        raise block("MANIFEST_SCHEMA_INVALID")
    return dict(value)


def parse_manifest(raw: bytes) -> AssetManifest:
    value = _load_json(raw)
    if not isinstance(value, dict) or set(value) != _TOP_KEYS:
        raise block("MANIFEST_SCHEMA_INVALID")
    group = value["asset_group"]
    version = value["group_version"]
    profiles = value["required_for_profiles"]
    rows = value["entries"]
    if (
        value["schema_version"] != 1
        or not isinstance(group, str)
        or not _NAME_RE.fullmatch(group)
        or type(version) is not int
        or not 1 <= version <= 2_147_483_647
        or not isinstance(profiles, list)
        or len(profiles) > MAX_PROFILE_COUNT
        or not all(isinstance(item, str) for item in profiles)
        or len(profiles) != len(set(profiles))
        or not set(profiles) <= _PROFILES
        or not isinstance(rows, list)
        or not 1 <= len(rows) <= MAX_MANIFEST_ENTRIES
    ):
        raise block("MANIFEST_SCHEMA_INVALID")

    entries: list[AssetEntry] = []
    roles: set[str] = set()
    paths: set[str] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not _ENTRY_REQUIRED <= set(row)
            or not set(row) <= _ENTRY_KEYS
        ):
            raise block("MANIFEST_SCHEMA_INVALID")
        role = row["role"]
        relative_path = validate_relative_path(row["relative_path"])
        size = row["size_bytes"]
        sha = row["sha256"]
        media_type = row["media_type"]
        validator = row["validator"]
        allow_empty = row.get("allow_empty", False)
        if (
            not isinstance(role, str)
            or not _ROLE_RE.fullmatch(role)
            or role in roles
            or relative_path in paths
            or type(size) is not int
            or not 0 <= size <= 1_099_511_627_776
            or (size == 0 and allow_empty is not True)
            or (
                size == 0
                and (
                    media_type != "text/plain"
                    or validator != "utf8_text"
                )
            )
            or not isinstance(sha, str)
            or not _SHA_RE.fullmatch(sha)
            or media_type not in _MEDIA_TYPES
            or not isinstance(validator, str)
            or not _ROLE_RE.fullmatch(validator)
            or type(allow_empty) is not bool
        ):
            raise block("MANIFEST_SCHEMA_INVALID")
        roles.add(role)
        paths.add(relative_path)
        entries.append(
            AssetEntry(
                role=role,
                relative_path=relative_path,
                size_bytes=size,
                sha256=sha,
                media_type=media_type,
                validator=validator,
                allow_empty=allow_empty,
                model_identity=_model_identity(row.get("model_identity")),
            )
        )
    if [entry.relative_path for entry in entries] != sorted(paths):
        raise block("MANIFEST_SCHEMA_INVALID")
    return AssetManifest(
        asset_group=group,
        group_version=version,
        required_for_profiles=tuple(profiles),
        entries=tuple(entries),
        digest=hashlib.sha256(raw).hexdigest(),
    )


def manifest_set_root(manifests: Iterable[AssetManifest]) -> str:
    leaves = [
        hashlib.sha256(f"{item.asset_group}\0{item.digest}".encode("utf-8")).digest()
        for item in sorted(manifests, key=lambda manifest: manifest.asset_group)
    ]
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256(leaves[index] + leaves[index + 1]).digest()
            for index in range(0, len(leaves), 2)
        ]
    return leaves[0].hex()
