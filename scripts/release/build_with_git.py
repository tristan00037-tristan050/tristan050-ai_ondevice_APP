#!/usr/bin/env python3
"""Create the immutable FirstScreen production BUILD_CONTEXT from a clean Git tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_trust import build_context_digest, canonical_json, validate_build_context
from scripts.release.firstscreen_source_contracts import changed_protected_paths


class BuildContextError(RuntimeError):
    pass


def _run(*arguments: str, root: Path) -> str:
    try:
        return subprocess.run(arguments, cwd=root, check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BuildContextError("BUILD_CONTEXT_GIT_FAILED") from exc


def _regular(path: Path, maximum: int = 128 * 1024 * 1024) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not 0 < metadata.st_size <= maximum:
        raise BuildContextError("BUILD_CONTEXT_INPUT_INVALID")
    return path.read_bytes()


def _digest(path: Path) -> str:
    return hashlib.sha256(_regular(path)).hexdigest()


def _created_at(raw: str) -> str:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise BuildContextError("BUILD_CONTEXT_COMMIT_TIME_INVALID") from exc
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-identity", required=True)
    parser.add_argument("--toolchain-identity", required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--python-lock", type=Path, default=Path("requirements-firstscreen-ci.lock"))
    parser.add_argument("--npm-lock", type=Path, default=Path("butler-desktop/package-lock.json"))
    parser.add_argument("--cargo-lock", type=Path, default=Path("butler-desktop/src-tauri/Cargo.lock"))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    commit = _run("git", "rev-parse", f"{arguments.commit}^{{commit}}", root=root)
    tree = _run("git", "rev-parse", f"{commit}^{{tree}}", root=root)
    baseline = _run("git", "rev-parse", f"{arguments.baseline}^{{commit}}", root=root)
    if _run("git", "status", "--porcelain", "--untracked-files=all", root=root):
        raise BuildContextError("BUILD_CONTEXT_REPOSITORY_NOT_CLEAN")
    if changed_protected_paths(baseline, commit, cwd=str(root)):
        raise BuildContextError("BUILD_CONTEXT_PROTECTED_SCOPE_CHANGED")
    source_bytes = _regular(arguments.source_manifest.resolve())
    try:
        source_manifest = json.loads(source_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BuildContextError("BUILD_CONTEXT_SOURCE_MANIFEST_INVALID") from exc
    if not isinstance(source_manifest, dict) or source_manifest.get("commit") != commit or source_manifest.get("tree") != tree:
        raise BuildContextError("BUILD_CONTEXT_SOURCE_IDENTITY_MISMATCH")
    document = {
        "schema_version": "butler.firstscreen.build-context.v1",
        "mode": "production",
        "repository": arguments.repository,
        "commit_oid": commit,
        "tree_oid": tree,
        "source_manifest_digest": hashlib.sha256(source_bytes).hexdigest(),
        "python_lock_digest": _digest((root / arguments.python_lock).resolve()),
        "npm_lock_digest": _digest((root / arguments.npm_lock).resolve()),
        "cargo_lock_digest": _digest((root / arguments.cargo_lock).resolve()),
        "toolchain_identity": arguments.toolchain_identity,
        "workflow_identity": arguments.workflow_identity,
        "created_at_utc": _created_at(_run("git", "show", "-s", "--format=%cI", commit, root=root)),
    }
    validate_build_context(document)
    payload = canonical_json(document)
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, output)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    print(
        json.dumps(
            {"BUILD_CONTEXT_OK": 1, "commit": commit, "tree": tree, "digest": build_context_digest(document)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildContextError as error:
        # Surface the specific failure code so the cause is diagnosable in CI.
        # BuildContextError messages are stable, path-free codes (e.g.
        # BUILD_CONTEXT_REPOSITORY_NOT_CLEAN, BUILD_CONTEXT_PROTECTED_SCOPE_CHANGED),
        # so the reason is exposed while no filesystem path leaks.
        print(f"BUILD_CONTEXT_OK=0 ERROR_CODE={error}")
        raise SystemExit(1)
    except Exception:
        # Unexpected failure: keep the generic code (no details) to avoid leaking
        # a path or internal message from an unclassified exception.
        print("BUILD_CONTEXT_OK=0 ERROR_CODE=BUILD_CONTEXT_INVALID")
        raise SystemExit(1)
