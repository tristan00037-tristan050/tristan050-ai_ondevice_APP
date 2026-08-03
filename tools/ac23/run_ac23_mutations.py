#!/usr/bin/env python3
"""Execute and summarize the twenty mandatory AC-23 mutation categories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


from verify_candidate_artifact_identity import load_evidence_policy, parse_junit_results


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: argparse.Namespace) -> Path:
    repository = args.repo.resolve()
    package = args.package.resolve()
    output = args.output.resolve()
    policy = load_evidence_policy(args.policy.resolve().read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    stem = output.with_suffix("")
    stdout_path = stem.with_suffix(".stdout.bin")
    stderr_path = stem.with_suffix(".stderr.bin")
    junit_path = stem.with_suffix(".xml")
    for path in (output, stdout_path, stderr_path, junit_path):
        if path.exists():
            raise ValueError("mutation output already exists")
    run_root = repository / ".ac23-mutation-run"
    if run_root.exists() or run_root.is_symlink():
        raise ValueError("mutation run path already exists")
    run_root.mkdir()
    raw_junit = run_root / "results.xml"
    pytest_tmp = run_root / "tmp"
    argv = [
            "python3",
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "tests/ac23/test_candidate_artifact_identity.py",
            "tests/ac23/test_evidence_semantics.py",
            "-k",
            "mutation or evidence_semantics_attack",
            "--junitxml=.ac23-mutation-run/results.xml",
            "--basetemp",
            ".ac23-mutation-run/tmp",
        ]
    start = _utc()
    try:
        env = {
            "PATH": os.fspath(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AC23_PACKAGE_ROOT": os.fspath(package),
            "BUTLER_APP_DATA_DIR": os.fspath(Path(pytest_tmp) / "app-data"),
        }
        completed = subprocess.run(argv, cwd=repository, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if raw_junit.is_file():
            junit_path.write_bytes(raw_junit.read_bytes())
    finally:
        import shutil
        shutil.rmtree(run_root, ignore_errors=True)
    end = _utc()
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    if completed.returncode != 0 or not junit_path.is_file():
        raise RuntimeError("mutation pytest failed")
    observed = parse_junit_results(junit_path.read_bytes())
    expected = {
        testcase
        for item in policy["legacy_mutation_categories"]
        for testcase in item["testcases"]
    } | {item["testcase"] for item in policy["evidence_semantic_cases"]}
    if observed != expected:
        raise RuntimeError("mutation testcase set mismatch")
    result = {
        "schema_version": "butler.box5.ac23-mutation-results.v2",
        "start_utc": start,
        "end_utc": end,
        "argv": [
            "python3",
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "tests/ac23/test_candidate_artifact_identity.py",
            "tests/ac23/test_evidence_semantics.py",
            "-k",
            "mutation or evidence_semantics_attack",
            "--junitxml=.ac23-mutation-run/results.xml",
            "--basetemp",
            ".ac23-mutation-run/tmp",
        ],
        "cwd": "candidate",
        "exit_code": completed.returncode,
        "legacy_categories": [
            {**item, "status": "PASS"}
            for item in policy["legacy_mutation_categories"]
        ],
        "evidence_semantic_cases": [
            {**item, "status": "PASS"}
            for item in policy["evidence_semantic_cases"]
        ],
        "stdout_path": "mutation/pytest_mutation.stdout.bin",
        "stdout_sha256": _sha256(stdout_path),
        "stderr_path": "mutation/pytest_mutation.stderr.bin",
        "stderr_sha256": _sha256(stderr_path),
        "junit_path": "mutation/pytest_mutation.xml",
        "junit_sha256": _sha256(junit_path),
        "summary": {
            "failed": 0,
            "legacy_categories_passed": 20,
            "legacy_subcases_passed": 27,
            "semantic_attacks_passed": 36,
        },
    }
    output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("evidence_policy_v2.json"),
    )
    try:
        result = run(parser.parse_args())
    except Exception:
        print('{"mutation_pass":0,"error_code":"E_MUTATION"}', file=sys.stderr)
        return 1
    print('{"mutation_pass":1,"error_code":""}')
    print(f"MUTATION_RESULTS={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
