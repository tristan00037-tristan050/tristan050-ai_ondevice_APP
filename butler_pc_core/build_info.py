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
import subprocess
from functools import lru_cache
from pathlib import Path

_UNKNOWN = "unknown"
_STAMP_NAME = "BUILD_INFO.json"


def _stamp_path() -> Path:
    # Bundled layout: <Resources>/butler_pc_core/build_info.py
    #             ->  <Resources>/BUILD_INFO.json  (sibling of the package dir)
    return Path(__file__).resolve().parent.parent / _STAMP_NAME


def _git_revision(revision: str) -> str:
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
    """Backward-compatible commit accessor used by existing health tests."""

    return _git_revision("HEAD")


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
        if isinstance(data, dict):
            merged = {
                "app": "Butler",
                "build_base_commit_oid": _UNKNOWN,
                "build_tree_oid": _UNKNOWN,
                "git_describe": _UNKNOWN,
                "build_timestamp_utc": _UNKNOWN,
                "app_version": _UNKNOWN,
                "a4_code_closure": None,
                "a4_authority_helper": {"bundled": False, "sha256": None},
                **data,
                "source": "bundled_stamp",
            }
            return merged
    # No stamp: best-effort git (dev tree), else unknown.
    return {
        "app": "Butler",
        "build_base_commit_oid": _git_head(),
        "build_tree_oid": _git_revision("HEAD^{tree}"),
        "git_describe": _UNKNOWN,
        "build_timestamp_utc": _UNKNOWN,
        "app_version": _UNKNOWN,
        "a4_code_closure": None,
        "a4_authority_helper": {"bundled": False, "sha256": None},
        "source": "runtime_fallback",
    }


def build_commit_oid() -> str:
    """Convenience accessor for the build-base commit OID (or ``"unknown"``)."""
    return str(build_info().get("build_base_commit_oid", _UNKNOWN))


def build_tree_oid() -> str:
    """Return the exact Git tree embedded by the build, or ``"unknown"``."""

    return str(build_info().get("build_tree_oid", _UNKNOWN))
