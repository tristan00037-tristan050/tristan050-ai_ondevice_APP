#!/usr/bin/env python3
"""Atomically write and verify the bundled Butler build provenance stamp."""
from __future__ import annotations

import argparse
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
    "git_describe",
    "build_timestamp_utc",
    "app_version",
    "builder",
}


class BuildInfoWriteError(RuntimeError):
    """Stable failure boundary for build provenance generation."""


def _validated_payload(
    *, build_oid: str, git_describe: str, timestamp_utc: str, app_version: str
) -> dict[str, str]:
    if not _OID_RE.fullmatch(build_oid):
        raise BuildInfoWriteError("INVALID_BUILD_OID")
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
        "git_describe": git_describe,
        "build_timestamp_utc": timestamp_utc,
        "app_version": app_version,
        "builder": "build_complete_app.sh",
    }


def _verify_payload(actual: object, expected: Mapping[str, str]) -> None:
    if not isinstance(actual, dict):
        raise BuildInfoWriteError("BUILD_INFO_NOT_OBJECT")
    if set(actual) != _REQUIRED_KEYS or actual != dict(expected):
        raise BuildInfoWriteError("BUILD_INFO_VERIFY_MISMATCH")


def write_build_info(
    output: Path,
    *,
    build_oid: str,
    git_describe: str,
    timestamp_utc: str,
    app_version: str,
) -> None:
    payload = _validated_payload(
        build_oid=build_oid,
        git_describe=git_describe,
        timestamp_utc=timestamp_utc,
        app_version=app_version,
    )
    if not output.parent.is_dir():
        raise BuildInfoWriteError("BUILD_INFO_PARENT_MISSING")

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
    parser.add_argument("--git-describe", required=True)
    parser.add_argument("--timestamp-utc", required=True)
    parser.add_argument("--app-version", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        write_build_info(
            args.output,
            build_oid=args.build_oid,
            git_describe=args.git_describe,
            timestamp_utc=args.timestamp_utc,
            app_version=args.app_version,
        )
    except BuildInfoWriteError as exc:
        print(f"BUILD_INFO_WRITE_OK=0 ERROR_CODE={exc}")
        return 1
    print("BUILD_INFO_WRITE_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
