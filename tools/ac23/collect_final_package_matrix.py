#!/usr/bin/env python3
"""Collect and independently verify the final AC-23 package normal matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from junit_closed_profile import parse_pytest_junit_closed
from verify_candidate_artifact_identity import VerificationError, load_evidence_policy


EXPECTED_IDS = frozenset(
    f"tests.ac23.test_candidate_artifact_identity::test_normal_{index:02d}_{suffix}"
    for index, suffix in enumerate(
        (
            "bundle_contains_head",
            "head_tree",
            "base_tree",
            "ancestry",
            "patch_digest",
            "patch_tree",
            "source_digest",
            "source_tree",
            "submitted_head",
            "all_trees_equal",
            "changed_paths",
            "evidence_digest",
            "contract_digest",
            "repository_url",
            "clean_inventory",
            "regression_evidence_has_no_unowned_mapping",
        ),
        1,
    )
)
EXPECTED_FILES = frozenset(
    {"command.json", "stdout.bin", "stderr.bin", "junit.xml", "canonical.json", "subject.json"}
)
NORMAL_ARGV = [
    "python3",
    "-m",
    "pytest",
    "-q",
    "--disable-warnings",
    "tests/ac23/test_candidate_artifact_identity.py",
    "-k",
    "normal",
    "--junitxml=.ac23-final-matrix/junit.xml",
    "--basetemp",
    ".ac23-final-matrix/tmp",
]


class MatrixError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def _subject(package: Path) -> dict[str, str]:
    identity_path = package / "IDENTITY" / "candidate_artifact_identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "butler.box5.ac23-final-matrix-subject.v1",
        "package_checksum_sha256": _sha256(package / "SHA256SUMS.txt"),
        "package_identity_sha256": _sha256(identity_path),
        "head_commit": identity["head_commit"],
        "head_tree": identity["head_tree"],
    }


def _limits(policy_path: Path) -> dict[str, int]:
    policy = load_evidence_policy(policy_path.read_bytes())
    return policy["limits"]


def verify(evidence: Path, package: Path, policy_path: Path) -> None:
    evidence = evidence.resolve()
    package = package.resolve()
    actual = {path.relative_to(evidence).as_posix() for path in evidence.rglob("*") if path.is_file()}
    if actual != EXPECTED_FILES or any(path.is_symlink() for path in evidence.rglob("*")):
        raise MatrixError("E_FINAL_MATRIX_INVENTORY")
    if json.loads((evidence / "subject.json").read_text(encoding="utf-8")) != _subject(package):
        raise MatrixError("E_FINAL_MATRIX_SUBJECT")
    command = json.loads((evidence / "command.json").read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "argv", "cwd", "start_utc", "end_utc", "exit_code", "termination",
        "stdout_path", "stdout_sha256", "stderr_path", "stderr_sha256", "junit_path", "junit_sha256",
        "canonical_path", "canonical_sha256",
    }
    if set(command) != expected_keys or command["schema_version"] != "butler.box5.ac23-final-matrix-command.v1":
        raise MatrixError("E_FINAL_MATRIX_SCHEMA")
    if command["argv"] != NORMAL_ARGV or command["cwd"] != "candidate" or command["exit_code"] != 0 or command["termination"] != "exit":
        raise MatrixError("E_FINAL_MATRIX_COMMAND")
    try:
        if datetime.fromisoformat(command["start_utc"].replace("Z", "+00:00")) > datetime.fromisoformat(command["end_utc"].replace("Z", "+00:00")):
            raise MatrixError("E_FINAL_MATRIX_TIMESTAMP")
    except (TypeError, ValueError) as error:
        raise MatrixError("E_FINAL_MATRIX_TIMESTAMP") from error
    for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256"), ("junit_path", "junit_sha256"), ("canonical_path", "canonical_sha256")):
        relative = command[path_key]
        if relative not in EXPECTED_FILES or _sha256(evidence / relative) != command[digest_key]:
            raise MatrixError("E_FINAL_MATRIX_RAW")
    limits = _limits(policy_path.resolve())
    result = parse_pytest_junit_closed(
        (evidence / "junit.xml").read_bytes(),
        expected_testcase_ids=EXPECTED_IDS,
        max_bytes=limits["max_junit_bytes"],
        max_elements=limits["max_xml_elements"],
        max_testcases_per_run=limits["max_testcases_per_run"],
        max_attribute_count_per_element=limits["max_attribute_count_per_element"],
        max_attribute_value_bytes=limits["max_attribute_value_bytes"],
        max_testcase_id_bytes=limits["max_testcase_id_bytes"],
    )
    if result.to_bytes() != (evidence / "canonical.json").read_bytes():
        raise MatrixError("E_FINAL_MATRIX_CANONICAL")


def collect(repo: Path, package: Path, output: Path, policy_path: Path) -> None:
    repo = repo.resolve()
    package = package.resolve()
    output = output.resolve()
    run_root = repo / ".ac23-final-matrix"
    if output.exists() or output.is_symlink() or run_root.exists() or run_root.is_symlink():
        raise MatrixError("E_FINAL_MATRIX_DESTINATION")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + ".staging")
    if staging.exists() or staging.is_symlink():
        raise MatrixError("E_FINAL_MATRIX_DESTINATION")
    staging.mkdir()
    run_root.mkdir()
    subject = _subject(package)
    start = _utc()
    actual_argv = [sys.executable, *NORMAL_ARGV[1:]]
    env = {
        "PATH": os.fspath(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
        "LC_ALL": "C", "LANG": "C", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
        "AC23_PACKAGE_ROOT": os.fspath(package),
        "BUTLER_APP_DATA_DIR": os.fspath(run_root / "app-data"),
    }
    try:
        completed = subprocess.run(actual_argv, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        end = _utc()
        junit_source = run_root / "junit.xml"
        if completed.returncode != 0 or not junit_source.is_file():
            raise MatrixError("E_FINAL_MATRIX_RUN")
        (staging / "stdout.bin").write_bytes(completed.stdout)
        (staging / "stderr.bin").write_bytes(completed.stderr)
        (staging / "junit.xml").write_bytes(junit_source.read_bytes())
        limits = _limits(policy_path.resolve())
        canonical = parse_pytest_junit_closed(
            (staging / "junit.xml").read_bytes(),
            expected_testcase_ids=EXPECTED_IDS,
            max_bytes=limits["max_junit_bytes"], max_elements=limits["max_xml_elements"],
            max_testcases_per_run=limits["max_testcases_per_run"],
            max_attribute_count_per_element=limits["max_attribute_count_per_element"],
            max_attribute_value_bytes=limits["max_attribute_value_bytes"],
            max_testcase_id_bytes=limits["max_testcase_id_bytes"],
        )
        (staging / "canonical.json").write_bytes(canonical.to_bytes())
        (staging / "subject.json").write_bytes(_canonical(subject))
        command = {
            "schema_version": "butler.box5.ac23-final-matrix-command.v1", "argv": NORMAL_ARGV,
            "cwd": "candidate", "start_utc": start, "end_utc": end,
            "exit_code": completed.returncode, "termination": "exit",
            "stdout_path": "stdout.bin", "stdout_sha256": _sha256(staging / "stdout.bin"),
            "stderr_path": "stderr.bin", "stderr_sha256": _sha256(staging / "stderr.bin"),
            "junit_path": "junit.xml", "junit_sha256": _sha256(staging / "junit.xml"),
            "canonical_path": "canonical.json", "canonical_sha256": _sha256(staging / "canonical.json"),
        }
        (staging / "command.json").write_bytes(_canonical(command))
        os.replace(staging, output)
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        if staging.exists():
            shutil.rmtree(staging)
    if _subject(package) != subject:
        raise MatrixError("E_FINAL_MATRIX_SUBJECT")
    verify(output, package, policy_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--repo", type=Path, required=True)
    collect_parser.add_argument("--package", type=Path, required=True)
    collect_parser.add_argument("--output", type=Path, required=True)
    collect_parser.add_argument("--policy", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--package", type=Path, required=True)
    verify_parser.add_argument("--evidence", type=Path, required=True)
    verify_parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "collect":
            collect(args.repo, args.package, args.output, args.policy)
        else:
            verify(args.evidence, args.package, args.policy)
    except (MatrixError, VerificationError, OSError, ValueError, KeyError):
        print('{"error_code":"E_FINAL_PACKAGE_MATRIX","final_package_matrix_pass":0}', file=sys.stderr)
        return 1
    print('{"error_code":"","final_package_matrix_pass":1}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
