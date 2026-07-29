#!/usr/bin/env python3
"""Generate or verify the protected FirstScreen verifier asset manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ASSETS = (
    "butler-desktop/acceptance/action-pins.v1.json",
    "butler-desktop/acceptance/required-tests.v3.json",
    "butler-desktop/scripts/verify-required-test-nodes.mjs",
    "contracts/evidence-index.schema.json",
    "scripts/ci/strict_json.mjs",
    "scripts/ci/trusted_firstscreen_artifact.py",
    "scripts/ci/trusted_firstscreen_historical.py",
    "scripts/ci/trusted_firstscreen_mutations.mjs",
    "scripts/ci/trusted_firstscreen_run.py",
    "scripts/ci/verify_trusted_firstscreen_package.py",
    "tests/firstscreen_trusted/fixtures/historical_attacks.v1.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(root: Path) -> dict[str, object]:
    rows = []
    for relative_name in ASSETS:
        path = root / relative_name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("PROTECTED_ASSET_INVALID")
        rows.append(
            {
                "path": relative_name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": 1,
        "assets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "butler-desktop/acceptance/trusted-verifier-assets.v1.json"
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    expected = (
        json.dumps(build(root), indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    manifest = root / args.manifest
    if args.check:
        if not manifest.is_file() or manifest.is_symlink():
            print("TRUSTED_VERIFIER_ASSET_MANIFEST_OK=0")
            print("ERROR_CODE=PROTECTED_ASSET_MANIFEST_MISSING")
            return 1
        if manifest.read_bytes() != expected:
            print("TRUSTED_VERIFIER_ASSET_MANIFEST_OK=0")
            print("ERROR_CODE=PROTECTED_ASSET_MANIFEST_DRIFT")
            return 1
    else:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            manifest,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            view = memoryview(expected)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise RuntimeError("PROTECTED_ASSET_MANIFEST_WRITE_FAILED")
                view = view[count:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    print("TRUSTED_VERIFIER_ASSET_MANIFEST_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
