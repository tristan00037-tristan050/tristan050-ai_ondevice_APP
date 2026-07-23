#!/usr/bin/env python3
"""Prepare the canonical A4 baseline manifest for external SSHSIG approval.

This utility never reads a private key and never creates an approval signature.
The repository owner signs the emitted manifest on the isolated approval device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


BASELINE_SCHEMA = "butler.box5.a4.secret_scan_baseline.v5.5"
MANIFEST_SCHEMA = "butler.box5.a4.secret_scan_baseline_manifest.v5.7"
SIGNATURE_NAMESPACE = "butler-a4-secret-baseline"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("git lineage verification failed")
    return completed.stdout.strip()


def prepare_manifest(*, repo: Path, baseline_path: Path, source_head: str) -> bytes:
    repo = repo.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", source_head):
        raise ValueError("source head is invalid")
    current_head = _git(repo, "rev-parse", "--verify", "HEAD")
    _git(repo, "merge-base", "--is-ancestor", source_head, current_head)

    baseline_bytes = baseline_path.read_bytes()
    document = json.loads(baseline_bytes.decode("utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != BASELINE_SCHEMA
        or document.get("source_head") != source_head
        or document.get("raw_paths_included") is not False
        or document.get("raw_values_included") is not False
        or not isinstance(document.get("entries"), list)
    ):
        raise ValueError("baseline is not bound to the requested source head")
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "approved_source_head": source_head,
        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "entry_count": len(document["entries"]),
    }
    return (
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest_bytes = prepare_manifest(
            repo=args.repo,
            baseline_path=args.baseline,
            source_head=args.source_head,
        )
        args.output.write_bytes(manifest_bytes)
    except Exception:
        print("A4_BASELINE_APPROVAL_PREPARED=0")
        print("ERROR_CODE=BASELINE_APPROVAL_PREPARATION_FAILED")
        return 2
    print("A4_BASELINE_APPROVAL_PREPARED=1")
    print(f"SIGNATURE_NAMESPACE={SIGNATURE_NAMESPACE}")
    print(f"MANIFEST_SHA256={hashlib.sha256(manifest_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
