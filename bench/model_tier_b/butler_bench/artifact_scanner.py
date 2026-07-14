from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import stat
import tarfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .canonical import sha256_file
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASCII_RULES: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("ABSOLUTE_HOME_PATH", re.compile(rb"(?:/Users/|/home/|/root/)[A-Za-z0-9._-]+(?:/|\b)")),
    ("BEARER_TOKEN", re.compile(rb"(?i)bearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}")),
    ("PRIVATE_KEY", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("SECRET_ASSIGNMENT", re.compile(rb"(?i)\b(?:api[_-]?key|secret|password|token|cookie)\s*[:=]\s*[^\s,;]{6,}")),
    ("RAW_EVIDENCE_FIELD", re.compile(rb'(?i)"(?:prompt|raw_output|reference_text|draft_text)"\s*:')),
)
_TEXT_ENCODINGS = ("ascii", "utf-8", "utf-16le", "utf-16be")
_PROFILE_KEYS = {"relative_path", "magic_hex", "mime", "sha256", "max_bytes", "archive"}
_POLICY_KEYS = {"schema_version", "unregistered_file_action", "unregistered_binary_action", "encodings", "max_depth", "max_entries", "max_total_expanded_bytes", "max_single_file_bytes", "max_compression_ratio", "registered_binary_profiles", "forbidden_path_kinds"}


@dataclass(frozen=True, slots=True)
class ScanLimits:
    max_depth: int
    max_entries: int
    max_total_expanded_bytes: int
    max_single_file_bytes: int
    max_compression_ratio: int


@dataclass(slots=True)
class ScanBudget:
    entries: int = 0
    expanded_bytes: int = 0


def scan_artifact_tree(root: Path, manifest: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve(strict=True)
    _validate_policy(policy)
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "self_exclusion", "files", "artifact_manifest_sha256"
    }:
        _block("MANIFEST_KEYS")
    declared: dict[str, tuple[int, str]] = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"relative_path", "size_bytes", "sha256"}:
            _block("MANIFEST_ENTRY")
        relative = _safe_relative(entry["relative_path"])
        if relative in declared or not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            _block("MANIFEST_DUPLICATE_OR_SIZE")
        if not isinstance(entry["sha256"], str) or not _SHA256.fullmatch(entry["sha256"]):
            _block("MANIFEST_DIGEST")
        declared[relative] = (entry["size_bytes"], entry["sha256"])
    profiles = _load_profiles(policy)
    limits = _load_limits(policy)
    actual: dict[str, tuple[int, str]] = {}
    casefold: dict[str, str] = {}
    findings: list[dict[str, Any]] = []
    budget = ScanBudget()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative == manifest["self_exclusion"]:
            continue
        _validate_filesystem_entry(path, relative)
        if not path.is_file():
            continue
        normalized = _safe_relative(relative)
        folded = unicodedata.normalize("NFC", normalized).casefold()
        if folded in casefold and casefold[folded] != normalized:
            _block("CASEFOLD_COLLISION")
        casefold[folded] = normalized
        size = path.stat().st_size
        digest = sha256_file(path)
        actual[normalized] = (size, digest)
        if declared.get(normalized) != (size, digest):
            _block("ARTIFACT_SET_OR_DIGEST")
        data = path.read_bytes()
        _scan_payload(normalized, data, profiles.get(normalized), limits, budget, findings, depth=0, profiles=profiles)
    if actual != declared:
        _block("ARTIFACT_SET_OR_DIGEST")
    if findings:
        raise GateError(FailClass.SECURITY_PRIVACY, findings[0]["rule_id"], exit_code=ExitCode.SECURITY)
    return {
        "schema_version": "butler.model-tier-b.raw-scan.v2.8",
        "files_scanned": len(actual),
        "expanded_entries_scanned": budget.entries,
        "expanded_bytes_scanned": budget.expanded_bytes,
        "finding_count": 0,
        "redaction_applied": False,
        "raw_zero_pass": True,
    }


def scan_bytes_all_encodings(data: bytes, *, file_sha256: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for encoding in _TEXT_ENCODINGS:
        try:
            decoded = data.decode(encoding)
        except UnicodeError:
            continue
        encoded = decoded.encode("utf-8", errors="strict")
        for rule_id, pattern in _ASCII_RULES:
            for match in pattern.finditer(encoded):
                key = (rule_id, match.start(), encoding.upper())
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "rule_id": rule_id,
                    "file_sha256": file_sha256,
                    "byte_range": [match.start(), match.end()],
                    "encoding": encoding.upper(),
                })
    return findings


def _scan_payload(
    relative: str,
    data: bytes,
    profile: dict[str, Any] | None,
    limits: ScanLimits,
    budget: ScanBudget,
    findings: list[dict[str, Any]],
    *,
    depth: int,
    profiles: dict[str, dict[str, Any]],
) -> None:
    if depth > limits.max_depth:
        _block("ARCHIVE_MAX_DEPTH")
    if len(data) > limits.max_single_file_bytes:
        _block("MAX_SINGLE_FILE_BYTES")
    budget.entries += 1
    budget.expanded_bytes += len(data)
    if budget.entries > limits.max_entries or budget.expanded_bytes > limits.max_total_expanded_bytes:
        _block("ARCHIVE_BUDGET")
    digest = hashlib.sha256(data).hexdigest()
    findings.extend(scan_bytes_all_encodings(data, file_sha256=digest))
    binary = b"\x00" in data or not _is_utf8_text(data)
    if binary and profile is None:
        _block("UNREGISTERED_BINARY")
    if profile is not None:
        _validate_binary_profile(relative, data, profile)
    is_zip = data.startswith(b"PK\x03\x04")
    is_gzip = data.startswith(b"\x1f\x8b")
    is_tar = len(data) > 262 and data[257:262] == b"ustar"
    if is_zip or is_gzip or is_tar:
        if profile is None or profile["archive"] is not True:
            _block("UNREGISTERED_ARCHIVE")
        _scan_archive(relative, data, profiles=profiles, limits=limits, budget=budget, findings=findings, depth=depth + 1)


def _scan_archive(
    relative: str,
    data: bytes,
    profiles: dict[str, dict[str, Any]],
    limits: ScanLimits,
    budget: ScanBudget,
    findings: list[dict[str, Any]],
    *,
    depth: int,
) -> None:
    if depth > limits.max_depth:
        _block("ARCHIVE_MAX_DEPTH")
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names: set[str] = set()
                folded: set[str] = set()
                for info in archive.infolist():
                    name = _safe_relative(info.filename)
                    fold = unicodedata.normalize("NFC", name).casefold()
                    if name in names or fold in folded:
                        _block("DUPLICATE_ARCHIVE_ENTRY")
                    names.add(name); folded.add(fold)
                    if info.is_dir():
                        continue
                    if info.file_size > limits.max_single_file_bytes:
                        _block("MAX_SINGLE_FILE_BYTES")
                    compressed = max(info.compress_size, 1)
                    if info.file_size > compressed * limits.max_compression_ratio:
                        _block("ARCHIVE_COMPRESSION_RATIO")
                    payload = archive.read(info)
                    member_path = f"{relative}!/{name}"
                    _scan_payload(member_path, payload, profiles.get(member_path), limits, budget, findings, depth=depth, profiles=profiles)
        except (zipfile.BadZipFile, RuntimeError, OSError):
            _block("ARCHIVE_INVALID")
        return
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            names: set[str] = set()
            folded: set[str] = set()
            for member in archive.getmembers():
                name = _safe_relative(member.name)
                fold = unicodedata.normalize("NFC", name).casefold()
                if name in names or fold in folded:
                    _block("DUPLICATE_ARCHIVE_ENTRY")
                names.add(name); folded.add(fold)
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    _block("ARCHIVE_SPECIAL_ENTRY")
                if not member.isfile():
                    continue
                if member.size > limits.max_single_file_bytes:
                    _block("MAX_SINGLE_FILE_BYTES")
                stream = archive.extractfile(member)
                if stream is None:
                    _block("ARCHIVE_ENTRY_READ")
                payload = stream.read(limits.max_single_file_bytes + 1)
                member_path = f"{relative}!/{name}"
                _scan_payload(member_path, payload, profiles.get(member_path), limits, budget, findings, depth=depth, profiles=profiles)
    except (tarfile.TarError, OSError):
        _block("ARCHIVE_INVALID")


def _load_profiles(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = policy.get("registered_binary_profiles")
    if not isinstance(values, list):
        _block("BINARY_PROFILE_LIST")
    result: dict[str, dict[str, Any]] = {}
    for profile in values:
        if not isinstance(profile, dict) or set(profile) != _PROFILE_KEYS:
            _block("BINARY_PROFILE_KEYS")
        relative = _safe_relative(profile["relative_path"])
        if relative in result:
            _block("BINARY_PROFILE_DUPLICATE")
        result[relative] = profile
    return result


def _validate_policy(policy: dict[str, Any]) -> None:
    if not isinstance(policy, dict) or set(policy) != _POLICY_KEYS:
        _block("SCANNER_POLICY_KEYS")
    if policy["schema_version"] != "butler.model-tier-b.scanner-policy.v2.8":
        _block("SCANNER_POLICY_VERSION")
    if policy["unregistered_file_action"] != "BLOCK" or policy["unregistered_binary_action"] != "BLOCK":
        _block("SCANNER_FAIL_OPEN_ACTION")
    if policy["encodings"] != ["ASCII", "UTF-8", "UTF-16LE", "UTF-16BE"]:
        _block("SCANNER_ENCODINGS")
    required_kinds = {"absolute", "parent_traversal", "symlink", "special", "casefold_collision"}
    if not isinstance(policy["forbidden_path_kinds"], list) or set(policy["forbidden_path_kinds"]) != required_kinds:
        _block("SCANNER_PATH_POLICY")


def _load_limits(policy: dict[str, Any]) -> ScanLimits:
    keys = ("max_depth", "max_entries", "max_total_expanded_bytes", "max_single_file_bytes", "max_compression_ratio")
    values = []
    for key in keys:
        value = policy.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            _block("SCANNER_LIMITS")
        values.append(value)
    return ScanLimits(*values)


def _validate_binary_profile(relative: str, data: bytes, profile: dict[str, Any]) -> None:
    if profile["relative_path"] != relative:
        _block("BINARY_PROFILE_PATH")
    if not isinstance(profile["magic_hex"], str) or not re.fullmatch(r"[0-9a-fA-F]{2,64}", profile["magic_hex"]):
        _block("BINARY_PROFILE_MAGIC")
    if not data.startswith(bytes.fromhex(profile["magic_hex"])):
        _block("BINARY_MAGIC_MISMATCH")
    if not isinstance(profile["sha256"], str) or hashlib.sha256(data).hexdigest() != profile["sha256"]:
        _block("BINARY_DIGEST_MISMATCH")
    if not isinstance(profile["max_bytes"], int) or len(data) > profile["max_bytes"]:
        _block("BINARY_SIZE")
    guessed = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    if profile["mime"] not in {guessed, "application/octet-stream"}:
        _block("BINARY_MIME")
    if type(profile["archive"]) is not bool:
        _block("BINARY_ARCHIVE_FLAG")


def _validate_filesystem_entry(path: Path, relative: str) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        _block("FILESYSTEM_SPECIAL_ENTRY")
    _safe_relative(relative)


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        _block("PATH_NORMALIZATION")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value or "\x00" in value:
        _block("PATH_TRAVERSAL")
    return path.as_posix().rstrip("/")


def _is_utf8_text(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return False
    return all(ch in "\n\r\t" or ord(ch) >= 0x20 for ch in text)


def _block(detail: str) -> None:
    raise GateError(FailClass.SECURITY_PRIVACY, detail, exit_code=ExitCode.SECURITY)
