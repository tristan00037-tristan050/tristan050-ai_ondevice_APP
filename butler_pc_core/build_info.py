"""Build provenance marker readable from inside the bundled app.

At build time ``scripts/build_complete_app.sh`` writes ``BUILD_INFO.json`` next to
the ``butler_pc_core`` package inside the app bundle (``Contents/Resources/``) so a
running install can report which commit it was built from — previously the .app
carried no in-bundle build/commit marker at all.

Absence is non-fatal: fields degrade to ``"unknown"`` (a dev tree, or an older
build that predates the stamp). Reading never raises and is cached.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from functools import lru_cache
from pathlib import Path

_UNKNOWN = "unknown"
_STAMP_NAME = "BUILD_INFO.json"
_OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SAFE_TEXT_RE = re.compile(r"[A-Za-z0-9._/+:-]{1,128}\Z")
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_REQUIRED_STAMP_KEYS = {
    "app", "build_base_commit_oid", "build_tree_oid", "git_describe",
    "build_timestamp_utc", "app_version", "builder",
}


def _stamp_path() -> Path:
    # Bundled layout: <Resources>/butler_pc_core/build_info.py
    #             ->  <Resources>/BUILD_INFO.json  (sibling of the package dir)
    return Path(__file__).resolve().parent.parent / _STAMP_NAME


def _git_oid(revision: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", revision],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _UNKNOWN
    oid = result.stdout.strip()
    return oid if result.returncode == 0 and oid else _UNKNOWN


def _git_head() -> str:
    return _git_oid("HEAD^{commit}")


def _git_tree() -> str:
    return _git_oid("HEAD^{tree}")


def _valid_stamp(data: object) -> bool:
    if not isinstance(data, dict) or set(data) != _REQUIRED_STAMP_KEYS:
        return False
    try:
        timestamp = str(data.get("build_timestamp_utc"))
        parsed_timestamp = datetime.strptime(timestamp, _UTC_TIMESTAMP_FORMAT)
        timestamp_valid = parsed_timestamp.strftime(_UTC_TIMESTAMP_FORMAT) == timestamp
    except (TypeError, ValueError):
        timestamp_valid = False
    return (
        data.get("app") == "Butler"
        and isinstance(data.get("build_base_commit_oid"), str)
        and bool(_OID_RE.fullmatch(data["build_base_commit_oid"]))
        and isinstance(data.get("build_tree_oid"), str)
        and bool(_OID_RE.fullmatch(data["build_tree_oid"]))
        and timestamp_valid
        and all(
            isinstance(data.get(key), str) and bool(_SAFE_TEXT_RE.fullmatch(data[key]))
            for key in ("git_describe", "app_version", "builder")
        )
    )


@lru_cache(maxsize=1)
def build_info() -> dict:
    """Return build provenance for the running app.

    Keys: app, build_base_commit_oid, git_describe, build_timestamp_utc,
    app_version, source. Always populated; missing values are ``"unknown"``.
    """
    stamp = _stamp_path()
    if stamp.is_file():
        try:
            data = json.loads(stamp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if _valid_stamp(data):
            return {**data, "source": "bundled_stamp"}
    # No stamp: best-effort git (dev tree), else unknown.
    return {
        "app": "Butler",
        "build_base_commit_oid": _git_head(),
        "build_tree_oid": _git_tree(),
        "git_describe": _UNKNOWN,
        "build_timestamp_utc": _UNKNOWN,
        "app_version": _UNKNOWN,
        "source": "runtime_fallback",
    }


def build_commit_oid() -> str:
    """Convenience accessor for the build-base commit OID (or ``"unknown"``)."""
    return str(build_info().get("build_base_commit_oid", _UNKNOWN))


def build_tree_oid() -> str:
    """Return the regular source tree OID bound into this build."""
    return str(build_info().get("build_tree_oid", _UNKNOWN))
