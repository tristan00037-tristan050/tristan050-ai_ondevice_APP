"""Fail-closed v4.4 changed-path allowlist."""
from __future__ import annotations

import argparse
from pathlib import Path

from .strict_receipt import StrictReceiptError, validate_unique_paths


EXACT = frozenset({
    ".github/workflows/box5-ac25-stage-a-smoke.yml",
    ".github/workflows/product-verify-repo-guards.yml",
    ".github/workflows/release.yml",
    "scripts/verify/verify_repo_contracts.sh",
    "scripts/ops/gen_artifact_chain_proof_v2.sh",
    "scripts/ops/write_external_json_atomic.py",
})
PREFIXES = (
    "scripts/ci/ac25/",
    "docs/box5/ac25/",
    "tests/box5_ac25/",
)
START_BASE = "5bf48ed1221c27bb7af8d160568943b6a32117f2"


def validate_allowed_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    validate_unique_paths(paths)
    denied = tuple(path for path in paths if path not in EXACT and not path.startswith(PREFIXES))
    if denied:
        raise StrictReceiptError("V44_DELTA_OUT_OF_SCOPE")
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.base != START_BASE:
            raise StrictReceiptError("PRECONDITION_MISMATCH")
        raw = Path(args.manifest).read_bytes()
        paths = tuple(part.decode("utf-8", "strict") for part in raw.split(b"\0") if part)
        validate_allowed_paths(paths)
    except (OSError, UnicodeDecodeError, StrictReceiptError) as exc:
        code = exc.code if isinstance(exc, StrictReceiptError) else "PRECONDITION_MISMATCH"
        print("V44_ALLOWED_DELTA=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("V44_ALLOWED_DELTA=1")
    print("ERROR_CODE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EXACT", "PREFIXES", "START_BASE", "validate_allowed_paths"]
