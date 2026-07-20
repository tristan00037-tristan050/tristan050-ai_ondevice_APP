#!/usr/bin/env python3
"""Atomically write and verify the bundled Butler build provenance stamp."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Mapping

_OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_REQUIRED_KEYS = {
    "app",
    "build_base_commit_oid",
    "build_tree_oid",
    "git_describe",
    "build_timestamp_utc",
    "app_version",
    "builder",
    "a4_code_closure",
    "a4_authority_helper",
}
_A4_CODE_FILES = (
    "butler_pc_core/a4_verifier/cli.py",
    "butler_pc_core/accounting/assignment/a4_store_schema_v32.py",
    "butler_pc_core/accounting/classify/reconciliation_v2.py",
    "butler_pc_core/accounting/classify/reconciliation_service_v2.py",
    "butler_pc_core/accounting/classify/source_snapshot_v2_1.py",
    "butler_pc_core/accounting/classify/verifier_authority.py",
    "butler_pc_core/accounting/classify/contracts/a4_v2/evidence_bundle.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/code_dictionary.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/release_manifest.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.production.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verifier_authority_trust.schema.json",
    "butler_pc_core/accounting/classify/contracts/a4_v31/verification_receipt.schema.json",
)


class BuildInfoWriteError(RuntimeError):
    """Stable failure boundary for build provenance generation."""


def _validated_payload(
    *,
    build_oid: str,
    build_tree_oid: str,
    git_describe: str,
    timestamp_utc: str,
    app_version: str,
) -> dict[str, object]:
    if not _OID_RE.fullmatch(build_oid):
        raise BuildInfoWriteError("INVALID_BUILD_OID")
    if not re.fullmatch(r"[0-9a-f]{40}", build_tree_oid):
        raise BuildInfoWriteError("INVALID_BUILD_TREE_OID")
    try:
        parsed_timestamp = datetime.strptime(timestamp_utc, _UTC_TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise BuildInfoWriteError("INVALID_BUILD_TIMESTAMP") from exc
    if parsed_timestamp.strftime(_UTC_TIMESTAMP_FORMAT) != timestamp_utc:
        raise BuildInfoWriteError("INVALID_BUILD_TIMESTAMP")
    if not app_version.strip() or app_version == "unknown":
        raise BuildInfoWriteError("INVALID_APP_VERSION")
    if not git_describe.strip():
        raise BuildInfoWriteError("INVALID_GIT_DESCRIBE")
    return {
        "app": "Butler",
        "build_base_commit_oid": build_oid,
        "build_tree_oid": build_tree_oid,
        "git_describe": git_describe,
        "build_timestamp_utc": timestamp_utc,
        "app_version": app_version,
        "builder": "build_complete_app.sh",
    }


def _a4_code_closure(resources_root: Path) -> dict[str, object]:
    files: dict[str, str] = {}
    for relative in _A4_CODE_FILES:
        path = resources_root / relative
        if not path.is_file() or path.is_symlink():
            raise BuildInfoWriteError("A4_CODE_CLOSURE_FILE_MISSING")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "butler.a4.code_closure.v3.1",
        "files": files,
        "digest": hashlib.sha256(canonical).hexdigest(),
    }


def _verify_payload(actual: object, expected: Mapping[str, object]) -> None:
    if not isinstance(actual, dict):
        raise BuildInfoWriteError("BUILD_INFO_NOT_OBJECT")
    if set(actual) != _REQUIRED_KEYS or actual != dict(expected):
        raise BuildInfoWriteError("BUILD_INFO_VERIFY_MISMATCH")


def _authority_helper(path: Path | None) -> dict[str, object]:
    if path is None:
        return {"bundled": False, "sha256": None}
    try:
        info = path.lstat()
        if not path.is_file() or path.is_symlink() or info.st_size < 1:
            raise BuildInfoWriteError("A4_AUTHORITY_HELPER_INVALID")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except BuildInfoWriteError:
        raise
    except OSError as exc:
        raise BuildInfoWriteError("A4_AUTHORITY_HELPER_INVALID") from exc
    return {"bundled": True, "sha256": digest}


def write_build_info(
    output: Path,
    *,
    build_oid: str,
    build_tree_oid: str,
    git_describe: str,
    timestamp_utc: str,
    app_version: str,
    authority_helper: Path | None = None,
) -> None:
    payload = _validated_payload(
        build_oid=build_oid,
        build_tree_oid=build_tree_oid,
        git_describe=git_describe,
        timestamp_utc=timestamp_utc,
        app_version=app_version,
    )
    if not output.parent.is_dir():
        raise BuildInfoWriteError("BUILD_INFO_PARENT_MISSING")
    payload["a4_code_closure"] = _a4_code_closure(output.parent)
    payload["a4_authority_helper"] = _authority_helper(authority_helper)

    fd = -1
    temporary_path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(raw_path)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        with temporary_path.open("r", encoding="utf-8") as handle:
            _verify_payload(json.load(handle), payload)
        os.replace(temporary_path, output)
        temporary_path = None

        with output.open("r", encoding="utf-8") as handle:
            _verify_payload(json.load(handle), payload)
        dir_fd = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BuildInfoWriteError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise BuildInfoWriteError("BUILD_INFO_WRITE_FAILED") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-oid", required=True)
    parser.add_argument("--build-tree-oid", required=True)
    parser.add_argument("--git-describe", required=True)
    parser.add_argument("--timestamp-utc", required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--authority-helper", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        write_build_info(
            args.output,
            build_oid=args.build_oid,
            build_tree_oid=args.build_tree_oid,
            git_describe=args.git_describe,
            timestamp_utc=args.timestamp_utc,
            app_version=args.app_version,
            authority_helper=args.authority_helper,
        )
    except BuildInfoWriteError as exc:
        print(f"BUILD_INFO_WRITE_OK=0 ERROR_CODE={exc}")
        return 1
    print("BUILD_INFO_WRITE_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
