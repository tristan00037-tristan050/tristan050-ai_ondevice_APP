"""Single authority for FirstScreen source-path and protected-scope contracts.

The builder, standalone source verifier, product-bundle verifier, tests, and CI
all import this module.  Keep it dependency-free so it can be shipped beside a
standalone verifier without importing the application.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import unicodedata
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


PORTABLE_PATH_POLICY = "NFC_CASEFOLD_WINDOWS_V1"
PROTECTED_SCOPE_SCHEMA = "butler.firstscreen.protected-scope.v2"
PROTECTED_CONTRACT_ID = "butler.firstscreen.accounting-review.immutable.v1"
PROTECTED_PATHS = (
    "butler-desktop/src/components/accounting_review",
    "butler-desktop/src/lib/accounting_review",
)
WINDOWS_FORBIDDEN = frozenset('<>:"\\|?*')
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
    | {f"COM{index}" for index in "¹²³"}
    | {f"LPT{index}" for index in "¹²³"}
)


class SourceContractError(RuntimeError):
    """Stable, non-sensitive source-contract failure."""


def _fail(code: str) -> None:
    raise SourceContractError(code)


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SourceContractError("CONTRACT_CANONICALIZATION_INVALID") from exc


def protected_contract_digest() -> str:
    return hashlib.sha256(
        canonical_json({"contract_id": PROTECTED_CONTRACT_ID, "protected_paths": list(PROTECTED_PATHS)})
    ).hexdigest()


def portable_component_key(component: str) -> str:
    normalized = unicodedata.normalize("NFC", component)
    if (
        not normalized
        or normalized in {".", ".."}
        or normalized.endswith((" ", "."))
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or any(character in WINDOWS_FORBIDDEN for character in normalized)
        or len(normalized.encode("utf-16-le")) // 2 > 255
    ):
        _fail("PORTABLE_PATH_INVALID")
    stem = normalized.split(".", 1)[0].rstrip(" .").upper()
    if stem in WINDOWS_RESERVED:
        _fail("PORTABLE_PATH_INVALID")
    return normalized.casefold()


def portable_path_key(raw: str) -> str:
    return "/".join(portable_component_key(component) for component in raw.split("/"))


def safe_relative_path(raw: object) -> PurePosixPath:
    if not isinstance(raw, str) or "\\" in raw or "\0" in raw:
        _fail("INVALID_MANIFEST_PATH")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or raw != path.as_posix():
        _fail("INVALID_MANIFEST_PATH")
    portable_path_key(raw)
    return path


def require_portable_unique(paths: Iterable[str], code: str) -> None:
    identities: dict[str, str] = {}
    for raw in paths:
        safe_relative_path(raw)
        key = portable_path_key(raw)
        if key in identities:
            _fail(code)
        identities[key] = raw


def is_protected_path(path: str) -> bool:
    candidate = safe_relative_path(path).as_posix()
    return any(candidate == root or candidate.startswith(root + "/") for root in PROTECTED_PATHS)


def protected_pathspecs() -> list[str]:
    return list(PROTECTED_PATHS)


def changed_protected_paths(baseline: str, target: str, *, cwd: str | None = None) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", baseline, target, "--", *PROTECTED_PATHS],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return [path for path in completed.stdout.splitlines() if path]


def _lower_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)


def validate_protected_scope(
    scope: object,
    *,
    target_commit: object,
    manifest_files: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    expected_keys = {
        "schema_version",
        "contract_id",
        "contract_digest",
        "baseline_commit",
        "target_commit",
        "protected_paths",
        "changed_paths",
        "verified_unchanged",
        "files",
    }
    if (
        not isinstance(scope, dict)
        or set(scope) != expected_keys
        or scope.get("schema_version") != PROTECTED_SCOPE_SCHEMA
        or scope.get("contract_id") != PROTECTED_CONTRACT_ID
        or scope.get("contract_digest") != protected_contract_digest()
        or scope.get("target_commit") != target_commit
        or scope.get("protected_paths") != list(PROTECTED_PATHS)
        or scope.get("changed_paths") != []
        or scope.get("verified_unchanged") is not True
        or not _lower_hex(scope.get("baseline_commit"), 40)
        or not _lower_hex(scope.get("target_commit"), 40)
        or not isinstance(scope.get("files"), list)
    ):
        _fail("MANIFEST_PROTECTED_SCOPE_INVALID")

    manifest_index = {item.get("path"): item for item in manifest_files if isinstance(item, Mapping)}
    records: list[dict[str, Any]] = []
    last_path: str | None = None
    for raw in scope["files"]:
        if not isinstance(raw, dict) or set(raw) != {"path", "mode", "blob", "sha256", "size"}:
            _fail("MANIFEST_PROTECTED_SCOPE_INVALID")
        path = safe_relative_path(raw.get("path")).as_posix()
        if not is_protected_path(path) or (last_path is not None and path.encode() <= last_path.encode()):
            _fail("MANIFEST_PROTECTED_SCOPE_INVALID")
        if (
            raw.get("mode") not in {"100644", "100755"}
            or not _lower_hex(raw.get("blob"), 40)
            or not _lower_hex(raw.get("sha256"), 64)
            or not isinstance(raw.get("size"), int)
            or raw["size"] < 0
        ):
            _fail("MANIFEST_PROTECTED_SCOPE_INVALID")
        manifest_record = manifest_index.get(path)
        if not isinstance(manifest_record, Mapping) or any(
            manifest_record.get(key) != raw[key] for key in ("mode", "blob", "sha256", "size")
        ):
            _fail("MANIFEST_PROTECTED_SCOPE_ARCHIVE_MISMATCH")
        records.append(raw)
        last_path = path

    expected = sorted(path for path in manifest_index if isinstance(path, str) and is_protected_path(path))
    if [record["path"] for record in records] != expected:
        _fail("MANIFEST_PROTECTED_SCOPE_SET_MISMATCH")
    return records


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-unchanged", nargs=2, metavar=("BASELINE", "TARGET"))
    parser.add_argument("--print-contract", action="store_true")
    arguments = parser.parse_args()
    if arguments.check_unchanged:
        changed = changed_protected_paths(*arguments.check_unchanged)
        if changed:
            print(json.dumps({"protected_scope_ok": False, "changed_paths": changed}, sort_keys=True))
            return 1
    print(json.dumps({
        "protected_scope_ok": True,
        "contract_id": PROTECTED_CONTRACT_ID,
        "contract_digest": protected_contract_digest(),
        "protected_paths": list(PROTECTED_PATHS),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
