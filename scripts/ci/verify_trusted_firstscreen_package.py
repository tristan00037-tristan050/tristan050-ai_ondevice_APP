#!/usr/bin/env python3
"""Run the protected required-node verifier against extracted evidence data."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

REPORT_ARGUMENTS = (
    ("--vitest", "reports/vitest-results.json"),
    ("--playwright", "reports/playwright-success.json"),
    ("--playwright", "reports/playwright-unavailable.json"),
    ("--pytest", "reports/contract-pytest.xml"),
    ("--pytest", "reports/authorities-pytest.xml"),
    ("--pytest", "reports/canonical-inputs-pytest.xml"),
    ("--pytest", "reports/product-integration-pytest.xml"),
    ("--pytest", "reports/windows-trust-pytest.xml"),
    ("--node", "reports/node-verifier-results.json"),
    ("--node", "reports/node-evidence-results.json"),
)
CONTEXTS = (
    "contexts/firstscreen-v9-unit-context.json",
    "contexts/firstscreen-v9-real-sidecar-context.json",
    "contexts/firstscreen-v9-real-sidecar-unavailable-context.json",
    "contexts/contract-context.json",
    "contexts/authorities-context.json",
    "contexts/canonical-inputs-context.json",
    "contexts/product-integration-context.json",
    "contexts/windows-trust-context.json",
    "contexts/node-verifier-context.json",
    "contexts/node-evidence-context.json",
)
ZERO_COUNTERS = (
    "missing",
    "duplicate_required_id",
    "duplicate_required_identity",
    "duplicate_actual_identity",
    "reused_actual",
    "skipped",
    "deselected",
    "xfail",
    "failed",
    "errors",
    "unexpected",
)


class VerifyError(RuntimeError):
    pass


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise VerifyError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _strict(path: Path, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_size < 1
        or metadata.st_size > max_bytes
    ):
        raise VerifyError("JSON_FILE_INVALID")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise VerifyError("JSON_BOM_FORBIDDEN")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                VerifyError("JSON_CONSTANT_INVALID")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifyError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise VerifyError("JSON_ROOT_INVALID")
    return value


def _safe_package(extraction_root: Path, relative_name: Any) -> Path:
    if not isinstance(relative_name, str) or "\\" in relative_name:
        raise VerifyError("PACKAGE_PATH_INVALID")
    pure = PurePosixPath(relative_name)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise VerifyError("PACKAGE_PATH_INVALID")
    root = extraction_root.resolve(strict=True)
    current = root
    for part in pure.parts:
        current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise VerifyError("PACKAGE_SYMLINK_FORBIDDEN")
    package = current.resolve(strict=True)
    if package.parent == root or root not in package.parents:
        raise VerifyError("PACKAGE_PATH_INVALID")
    if not package.is_dir():
        raise VerifyError("PACKAGE_DIRECTORY_INVALID")
    return package


def verify(
    *,
    repository_root: Path,
    extraction_root: Path,
    preflight_path: Path,
    metadata_path: Path,
    event_path: Path,
    output_path: Path,
) -> None:
    preflight = _strict(preflight_path)
    metadata = _strict(metadata_path)
    package = _safe_package(extraction_root, preflight.get("package_relative"))
    producer = metadata.get("producer")
    tree = metadata.get("tree_oid")
    trusted = metadata.get("trusted_verifier")
    if (
        metadata.get("schema_version") != 1
        or not isinstance(producer, dict)
        or not isinstance(tree, dict)
        or not isinstance(trusted, dict)
    ):
        raise VerifyError("TRUSTED_METADATA_INVALID")

    command = [
        "node",
        str(
            repository_root
            / "butler-desktop"
            / "scripts"
            / "verify-required-test-nodes.mjs"
        ),
        "--manifest",
        str(repository_root / "butler-desktop/acceptance/required-tests.v3.json"),
    ]
    for flag, relative_name in REPORT_ARGUMENTS:
        command.extend((flag, str(package / relative_name)))
    for relative_name in CONTEXTS:
        command.extend(("--context", str(package / relative_name)))
    command.extend(
        (
            "--event",
            str(event_path),
            "--event-name",
            str(metadata.get("event_name")),
            "--pull-request",
            str(metadata.get("pull_request")),
            "--head",
            str(metadata.get("subject_head")),
            "--checkout-head",
            str(metadata.get("subject_head")),
            "--checkout-tree",
            str(tree.get("hex")),
            "--object-format",
            str(tree.get("algorithm")),
            "--producer-run-id",
            str(producer.get("run_id")),
            "--producer-run-attempt",
            str(producer.get("run_attempt")),
            "--producer-workflow-ref",
            str(producer.get("workflow_ref")),
            "--trusted-mode",
            "1",
            "--trusted-verifier-head",
            str(trusted.get("head")),
            "--trusted-verifier-tree",
            str(trusted.get("tree")),
            "--evidence-root",
            str(package),
            "--root",
            str(repository_root),
            "--output",
            str(output_path),
        )
    )
    completed = subprocess.run(
        command,
        cwd=repository_root,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
        env={**os.environ, "NO_COLOR": "1"},
    )
    if completed.returncode != 0:
        codes = re.findall(r"^ERROR_CODE=([A-Z0-9_:.-]+)$", completed.stdout, re.M)
        raise VerifyError(codes[-1] if codes else "REQUIRED_NODE_VERIFIER_FAILED")
    summary = _strict(output_path, max_bytes=4 * 1024 * 1024)
    if (
        summary.get("subject_head") != metadata.get("subject_head")
        or summary.get("required_total") != 92
        or summary.get("actual_total") != 92
        or summary.get("matched_total") != 92
        or summary.get("failed_total") != 0
        or any(summary.get(name) != 0 for name in ZERO_COUNTERS)
    ):
        raise VerifyError("REQUIRED_NODE_SUMMARY_INVALID")
    print("TRUSTED_REQUIRED_TESTS_OK=1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--extraction-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(
            repository_root=args.repository_root,
            extraction_root=args.extraction_root,
            preflight_path=args.preflight,
            metadata_path=args.metadata,
            event_path=args.event,
            output_path=args.output,
        )
    except (OSError, subprocess.SubprocessError, VerifyError, ValueError) as exc:
        code = str(exc) if re.fullmatch(r"[A-Z0-9_:.-]+", str(exc)) else "TRUSTED_PACKAGE_VERIFY_FAILED"
        print("TRUSTED_REQUIRED_TESTS_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
