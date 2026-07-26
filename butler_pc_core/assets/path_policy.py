from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from .errors import block

MAX_PATH_BYTES = 1024
MAX_SEGMENT_BYTES = 255
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_RESERVED_WINDOWS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise block("PATH_POLICY_VIOLATION")
    if value != unicodedata.normalize("NFC", value):
        raise block("PATH_POLICY_VIOLATION")
    if len(value.encode("utf-8")) > MAX_PATH_BYTES:
        raise block("RESOURCE_LIMIT_EXCEEDED")
    if (
        value in {".", ".."}
        or value.startswith(("/", "~", "\\"))
        or value.endswith("/")
        or "\\" in value
        or ":" in value
        or _DRIVE_RE.match(value)
        or _CONTROL_RE.search(value)
    ):
        raise block("PATH_POLICY_VIOLATION")

    parts = value.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise block("PATH_POLICY_VIOLATION")
    for part in parts:
        if len(part.encode("utf-8")) > MAX_SEGMENT_BYTES:
            raise block("RESOURCE_LIMIT_EXCEEDED")
        if part.endswith((" ", ".")):
            raise block("PATH_POLICY_VIOLATION")
        stem = part.split(".", 1)[0].upper()
        if stem in _RESERVED_WINDOWS:
            raise block("PATH_POLICY_VIOLATION")
    if PurePosixPath(value).as_posix() != value:
        raise block("PATH_POLICY_VIOLATION")
    return value
