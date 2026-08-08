"""Lossless, order-preserving parser for the repository-contract stdout."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum


CONTRACT_OUTPUT_NOT_UTF8 = "CONTRACT_OUTPUT_NOT_UTF8"
CONTRACT_PRIMARY_GUARD_INVALID = "CONTRACT_PRIMARY_GUARD_INVALID"
CONTRACT_DUPLICATE_PRIMARY = "CONTRACT_DUPLICATE_PRIMARY"
CONTRACT_MISSING_PRIMARY = "CONTRACT_MISSING_PRIMARY"
CONTRACT_DUPLICATE_GUARD = "CONTRACT_DUPLICATE_GUARD"
CONTRACT_DUPLICATE_KEY = CONTRACT_DUPLICATE_GUARD  # compatibility name
CONTRACT_UNKNOWN_LINE = "CONTRACT_UNKNOWN_LINE"
CONTRACT_MALFORMED_GUARD_KEY = "CONTRACT_MALFORMED_GUARD_KEY"
PARSE_OK = "NONE"

PRIMARY_KEY = "REPO_CONTRACTS_FAILED_GUARD"
PRIMARY_UNPARSED = "UNPARSED"
PRIMARY_UNPARSED_DUPLICATE = "UNPARSED_DUPLICATE"

_KEY_LINE_RE = re.compile(r"\A([A-Z][A-Z0-9_]{2,79})=([01]|[A-Za-z0-9_.:+/-]{1,120})\Z")
_META_LINE_RE = re.compile(r"\A([A-Z][A-Z0-9_]{2,79})=([A-Za-z0-9 ._:/()+-]{1,180})\Z")
_GUARD_KEY_RE = re.compile(r"\A[A-Z][A-Z0-9_]{0,76}_OK\Z")
_FIXED_META_KEYS = frozenset(
    {
        "DOD_KV_BLOCK_BEGIN", "DOD_KV_BLOCK_END", "ERROR_CODE", "P0_02_KEYS_ONLY_VAL",
        "REPO_CONTRACTS_LAST_GUARD",
    }
)
_META_KEY_RE = re.compile(r"\A[A-Z][A-Z0-9_]{0,70}_SKIPPED\Z")
_BLOCK_LINE_RE = re.compile(r"\ABLOCK: [A-Za-z0-9 ._:/()<>=-]{1,180}\Z")
_FAIL_LINE_RE = re.compile(r"\AFAIL: [A-Za-z0-9 ._:/()<>=-]{1,180}\Z")
# Banners are bounded meta-only labels, not inventory.  Existing canonical
# labels contain `~`, comparison operators, and Korean text; forbid controls
# while preserving those exact UTF-8 lines and their order.
_BANNER_LINE_RE = re.compile(r"\A== guard: [^\x00-\x1f\x7f]{1,180} ==\Z")
_SKIP_LINE_RE = re.compile(r"\ASKIP: [A-Za-z0-9 ,._:/()=+-]{1,180}\Z")
_BLOCK_LINE_LIMIT = 8
_PRIMARY_VALUE_RE = re.compile(r"\A[A-Za-z0-9 ._:/()\-]+\Z")
_PRIMARY_MAX_BYTES = 160


class ContractLineKind(str, Enum):
    PRIMARY = "PRIMARY"
    GUARD = "GUARD"
    META = "META"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ContractLine:
    ordinal: int
    kind: ContractLineKind
    key: str | None
    value: str | None
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class ContractObservation:
    lines: tuple[ContractLine, ...]
    primary_value: str
    guard_items: tuple[tuple[int, str, str], ...]
    failures: tuple[str, ...]
    meta_items: tuple[tuple[int, str | None, str | None], ...]
    unknown_line_count: int
    unknown_total_bytes: int
    unknown_manifest_sha256: str
    parse_error_code: str


@dataclass(frozen=True)
class ContractParseResult:
    keys: tuple[tuple[str, str], ...]
    primary_failed_guard: str
    failing_guard_keys: tuple[str, ...]
    block_lines: tuple[str, ...]
    unparsed_line_count: int
    unparsed_total_bytes: int
    unparsed_manifest_sha256: str
    primary_line_sha256: str
    primary_line_bytes: int
    parse_error_code: str
    observation: ContractObservation


def _canonical_manifest_sha256(entries: list[dict]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_primary_value(value: str) -> bool:
    return bool(value) and len(value.encode("utf-8")) <= _PRIMARY_MAX_BYTES and bool(
        _PRIMARY_VALUE_RE.fullmatch(value)
    )


def _line(ordinal: int, kind: ContractLineKind, raw: bytes, key=None, value=None) -> ContractLine:
    return ContractLine(
        ordinal=ordinal,
        kind=kind,
        key=key,
        value=value,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )


def parse_contract_observation(stdout: bytes) -> ContractObservation:
    try:
        text = stdout.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return ContractObservation(
            (), PRIMARY_UNPARSED, (), (), (), 0, 0,
            _canonical_manifest_sha256([]), CONTRACT_OUTPUT_NOT_UTF8,
        )

    lines: list[ContractLine] = []
    primary: list[tuple[str, bytes]] = []
    guards: list[tuple[int, str, str]] = []
    meta: list[tuple[int, str | None, str | None]] = []
    unknown_manifest: list[dict] = []
    unknown_bytes = 0
    malformed_guard = False
    invalid_primary = False
    seen_guards: set[str] = set()
    duplicate_guard = False
    block_count = 0

    for ordinal, value_line in enumerate(text.splitlines()):
        if not value_line.strip():
            continue
        raw = value_line.encode("utf-8")
        if value_line.startswith(PRIMARY_KEY + "="):
            value = value_line[len(PRIMARY_KEY) + 1:]
            primary.append((value, raw))
            if not _valid_primary_value(value):
                invalid_primary = True
            lines.append(_line(ordinal, ContractLineKind.PRIMARY, raw, PRIMARY_KEY, value))
            continue

        meta_match = _META_LINE_RE.fullmatch(value_line)
        if meta_match is not None:
            meta_key, meta_value = meta_match.groups()
            if meta_key in _FIXED_META_KEYS or _META_KEY_RE.fullmatch(meta_key):
                meta.append((ordinal, meta_key, meta_value))
                lines.append(_line(ordinal, ContractLineKind.META, raw, meta_key, meta_value))
                continue

        match = _KEY_LINE_RE.fullmatch(value_line)
        if match is not None:
            key, value = match.groups()
            if key.endswith("_OK"):
                if _GUARD_KEY_RE.fullmatch(key) is None or value not in ("0", "1"):
                    malformed_guard = True
                    lines.append(_line(ordinal, ContractLineKind.UNKNOWN, raw))
                else:
                    if key in seen_guards:
                        duplicate_guard = True
                    seen_guards.add(key)
                    # Policy ordinals are guard-only ordinals.  The raw-line
                    # ordinal remains available on ContractLine.
                    guards.append((len(guards), key, value))
                    lines.append(_line(ordinal, ContractLineKind.GUARD, raw, key, value))
                continue
        key_part, separator, _remainder = value_line.partition("=")
        if separator and key_part.endswith("_OK"):
            malformed_guard = True
        is_block = _BLOCK_LINE_RE.fullmatch(value_line) is not None and block_count < _BLOCK_LINE_LIMIT
        if is_block:
            block_count += 1
        if (
            is_block
            or _FAIL_LINE_RE.fullmatch(value_line)
            or _BANNER_LINE_RE.fullmatch(value_line)
            or _SKIP_LINE_RE.fullmatch(value_line)
        ):
            meta.append((ordinal, None, None))
            lines.append(_line(ordinal, ContractLineKind.META, raw))
            continue
        lines.append(_line(ordinal, ContractLineKind.UNKNOWN, raw))
        unknown_manifest.append({"ordinal": ordinal, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        unknown_bytes += len(raw)

    if len(primary) > 1:
        primary_value = PRIMARY_UNPARSED_DUPLICATE
        error = CONTRACT_DUPLICATE_PRIMARY
    elif not primary:
        primary_value = PRIMARY_UNPARSED
        error = CONTRACT_MISSING_PRIMARY
    elif invalid_primary:
        primary_value = PRIMARY_UNPARSED
        error = CONTRACT_PRIMARY_GUARD_INVALID
    else:
        primary_value = primary[0][0]
        error = PARSE_OK
    if malformed_guard and error == PARSE_OK:
        error = CONTRACT_MALFORMED_GUARD_KEY
    if duplicate_guard and error == PARSE_OK:
        error = CONTRACT_DUPLICATE_GUARD
    if unknown_manifest and error == PARSE_OK:
        error = CONTRACT_UNKNOWN_LINE
    return ContractObservation(
        lines=tuple(lines),
        primary_value=primary_value,
        guard_items=tuple(guards),
        failures=tuple(key for _ordinal, key, value in guards if value == "0"),
        meta_items=tuple(meta),
        unknown_line_count=len(unknown_manifest),
        unknown_total_bytes=unknown_bytes,
        unknown_manifest_sha256=_canonical_manifest_sha256(unknown_manifest),
        parse_error_code=error,
    )


def parse_contract_output(stdout: bytes) -> ContractParseResult:
    observation = parse_contract_observation(stdout)
    primary_lines = [line for line in observation.lines if line.kind is ContractLineKind.PRIMARY]
    block_lines: list[str] = []
    try:
        decoded = stdout.decode("utf-8", "strict")
    except UnicodeDecodeError:
        decoded = ""
    for line in decoded.splitlines():
        if _BLOCK_LINE_RE.fullmatch(line) and len(block_lines) < _BLOCK_LINE_LIMIT:
            block_lines.append(line)
    keys = tuple(
        (line.key, line.value)
        for line in observation.lines
        if line.key is not None and line.value is not None and line.kind in {ContractLineKind.GUARD, ContractLineKind.META}
    )
    if len(primary_lines) == 1:
        primary_sha = primary_lines[0].sha256
        primary_bytes = primary_lines[0].byte_count
    elif primary_lines:
        primary_sha = _canonical_manifest_sha256(
            [{"ordinal": line.ordinal, "sha256": line.sha256, "bytes": line.byte_count} for line in primary_lines]
        )
        primary_bytes = sum(line.byte_count for line in primary_lines)
    else:
        primary_sha = ""
        primary_bytes = 0
    return ContractParseResult(
        keys=keys,
        primary_failed_guard=observation.primary_value,
        failing_guard_keys=tuple(sorted(set(observation.failures))),
        block_lines=tuple(block_lines),
        unparsed_line_count=observation.unknown_line_count,
        unparsed_total_bytes=observation.unknown_total_bytes,
        unparsed_manifest_sha256=observation.unknown_manifest_sha256,
        primary_line_sha256=primary_sha,
        primary_line_bytes=primary_bytes,
        parse_error_code=observation.parse_error_code,
        observation=observation,
    )


def resolve_primary(result: ContractParseResult, *, exit_code: int) -> str:
    del exit_code
    return result.primary_failed_guard


def failing_keys_sha256(failing: tuple[str, ...]) -> str:
    payload = json.dumps(list(failing), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [name for name in globals() if name.startswith("CONTRACT_") or name in {
    "PARSE_OK", "PRIMARY_KEY", "PRIMARY_UNPARSED", "PRIMARY_UNPARSED_DUPLICATE",
    "ContractLineKind", "ContractLine", "ContractObservation", "ContractParseResult",
    "parse_contract_observation", "parse_contract_output", "resolve_primary", "failing_keys_sha256",
}]
