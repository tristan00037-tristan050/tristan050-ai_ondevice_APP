#!/usr/bin/env python3
"""Fail-closed semantic verifier for the canonical Box5 pytest JUnit artifact."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.trusted_parse_junit_xml import MAX_BYTES, parse_bytes


MINIMUM_TESTS = 382
REQUIRED_RUNNER = "pytest"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def verify(path: Path, expected_sha256: str) -> dict[str, int | str]:
    if not _DIGEST.fullmatch(expected_sha256):
        raise ValueError("JUNIT_EXPECTED_DIGEST_INVALID")
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or metadata.st_size > MAX_BYTES:
        raise ValueError("JUNIT_FILE_INVALID")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("JUNIT_DIGEST_MISMATCH")
    nodes = parse_bytes(raw)
    if len(nodes) < MINIMUM_TESTS:
        raise ValueError("JUNIT_TEST_COUNT_BELOW_POLICY")
    if any(node["runner"] != REQUIRED_RUNNER for node in nodes):
        raise ValueError("JUNIT_RUNNER_MISMATCH")
    failures = sum(node["status"] == "failed" for node in nodes)
    errors = sum(node["status"] == "error" for node in nodes)
    skipped = sum(node["status"] == "skipped" for node in nodes)
    if failures or errors:
        raise ValueError("JUNIT_NOT_GREEN")
    return {
        "sha256": digest,
        "tests": len(nodes),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    try:
        result = verify(arguments.junit, arguments.expected_sha256)
    except (OSError, ValueError) as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 96:
            code = "JUNIT_EVIDENCE_VERIFICATION_FAILED"
        print("STATUS=BLOCK")
        print(f"ERROR_CODE={code}")
        return 1
    print("STATUS=PASS")
    print(f"JUNIT_SHA256={result['sha256']}")
    print(f"TESTS={result['tests']}")
    print(f"FAILURES={result['failures']}")
    print(f"ERRORS={result['errors']}")
    print(f"SKIPPED={result['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
