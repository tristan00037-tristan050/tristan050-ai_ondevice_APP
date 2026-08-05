#!/usr/bin/env python3
"""Fail-closed Helper1 v6.1 baseline tree verifier."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-f]{40}$")
EXIT_BLOCKED = 42


def _git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def verify(repository: Path, expected_tree: str, expected_commit: str | None) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "butler.helper1.start-tree-verdict.v1",
        "expected_tree": expected_tree,
        "expected_commit": expected_commit,
        "observed_tree": None,
        "verified": False,
        "error_code": None,
    }
    if SHA40.fullmatch(expected_tree) is None or (
        expected_commit is not None and SHA40.fullmatch(expected_commit) is None
    ):
        result["error_code"] = "START_TREE_MISSING"
        return result
    try:
        if not repository.is_dir():
            raise OSError
        object_type = _git(repository, "cat-file", "-t", expected_tree).stdout.strip()
        if object_type != "tree":
            result["error_code"] = "START_TREE_MISSING"
            return result
        if expected_commit is not None:
            commit_type = _git(repository, "cat-file", "-t", expected_commit).stdout.strip()
            commit_tree = _git(repository, "rev-parse", f"{expected_commit}^{{tree}}").stdout.strip()
            if commit_type != "commit" or commit_tree != expected_tree:
                result["error_code"] = "START_TREE_MISMATCH"
                return result
        observed = _git(repository, "write-tree").stdout.strip()
        result["observed_tree"] = observed
        if observed != expected_tree:
            result["error_code"] = "START_TREE_MISMATCH"
            return result
        if _git(repository, "status", "--porcelain=v1", "--untracked-files=no").stdout:
            result["error_code"] = "START_TREE_DIRTY"
            return result
        submodules = _git(repository, "submodule", "status", "--recursive", check=False)
        if submodules.returncode != 0 or any(
            line[:1] in {"-", "+", "U"} for line in submodules.stdout.splitlines() if line
        ):
            result["error_code"] = "START_TREE_CLOSURE_INCOMPLETE"
            return result
        pointer_scan = _git(
            repository,
            "grep",
            "-Il",
            "version https://git-lfs.github.com/spec/v1",
            "--",
            check=False,
        )
        if pointer_scan.returncode not in {0, 1}:
            result["error_code"] = "START_TREE_CLOSURE_INCOMPLETE"
            return result
        if pointer_scan.returncode == 0 and pointer_scan.stdout.strip():
            lfs = subprocess.run(
                ["git", "-C", str(repository), "lfs", "fsck"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if lfs.returncode != 0:
                result["error_code"] = "START_TREE_CLOSURE_INCOMPLETE"
                return result
    except (OSError, subprocess.SubprocessError):
        result["error_code"] = "START_TREE_MISSING"
        return result
    result["verified"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    verdict = verify(args.repository.resolve(), args.expected_tree, args.expected_commit)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp-{os.getpid()}")
        temporary.write_text(_canonical(verdict), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, args.output)
    except OSError:
        print("HELPER1_START_TREE_OK=0")
        print("ERROR_CODE=START_TREE_MISSING")
        return EXIT_BLOCKED
    ok = verdict["verified"] is True
    print(f"HELPER1_START_TREE_OK={int(ok)}")
    print(f"ERROR_CODE={verdict['error_code'] or 'NONE'}")
    return 0 if ok else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
