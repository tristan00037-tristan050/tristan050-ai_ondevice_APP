from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .errors import ExitCode, FailClass, GateError

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_INTEGER = re.compile(r"^-?(0|[1-9][0-9]*)$")
_DECIMAL = re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+$")


def load_strict_yaml_mapping(path: Path) -> dict[str, Any]:
    """Parse the small, duplicate-safe YAML subset used by benchmark policy.

    Supported: mappings, two-space indentation, strings, booleans, integers,
    and decimal scalars.  Anchors, aliases, tags, sequences, merge keys, and
    implicit timestamps are rejected to keep policy bytes reviewable.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise GateError(FailClass.POLICY_INCOMPLETE, "POLICY_READ_FAILED", exit_code=ExitCode.SCHEMA) from None
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-2, root)]
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw or raw.rstrip() != raw:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_WHITESPACE_L{line_number}", exit_code=ExitCode.SCHEMA)
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_INDENT_L{line_number}", exit_code=ExitCode.SCHEMA)
        content = raw[indent:]
        if any(token in content for token in ("&", "*", "!!", "<<:", "[", "]", "{", "}")):
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_FEATURE_L{line_number}", exit_code=ExitCode.SCHEMA)
        if ":" not in content:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_MAPPING_L{line_number}", exit_code=ExitCode.SCHEMA)
        key, scalar = content.split(":", 1)
        if not _KEY.fullmatch(key):
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_KEY_L{line_number}", exit_code=ExitCode.SCHEMA)
        scalar = scalar.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack or indent != stack[-1][0] + 2:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_DEPTH_L{line_number}", exit_code=ExitCode.SCHEMA)
        target = stack[-1][1]
        if key in target:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_DUPLICATE_L{line_number}", exit_code=ExitCode.SCHEMA)
        if not scalar:
            child: dict[str, Any] = {}
            target[key] = child
            stack.append((indent, child))
        else:
            target[key] = _parse_scalar(scalar, line_number)
    return root


def _parse_scalar(raw: str, line_number: int) -> object:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if _INTEGER.fullmatch(raw):
        return int(raw)
    if _DECIMAL.fullmatch(raw):
        try:
            return Decimal(raw)
        except InvalidOperation:
            pass
    if raw.startswith(('"', "'")) or raw.endswith(('"', "'")):
        if len(raw) < 2 or raw[0] != raw[-1] or raw[0] not in {'"', "'"}:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_QUOTE_L{line_number}", exit_code=ExitCode.SCHEMA)
        value = raw[1:-1]
        if raw[0] == '"' and "\\" in value:
            raise GateError(FailClass.SCHEMA_INVALID, f"YAML_ESCAPE_L{line_number}", exit_code=ExitCode.SCHEMA)
        return value
    if " #" in raw:
        raw = raw.split(" #", 1)[0].rstrip()
    if not raw or raw.startswith(("- ", "? ")):
        raise GateError(FailClass.SCHEMA_INVALID, f"YAML_SCALAR_L{line_number}", exit_code=ExitCode.SCHEMA)
    return raw


def normalize_decimals(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise GateError(FailClass.SCHEMA_INVALID, "NONFINITE_POLICY_NUMBER", exit_code=ExitCode.SCHEMA)
        return format(value.normalize(), "f")
    if isinstance(value, dict):
        return {key: normalize_decimals(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_decimals(item) for item in value]
    return value

