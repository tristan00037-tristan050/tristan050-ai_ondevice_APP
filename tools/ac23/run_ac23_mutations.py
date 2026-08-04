#!/usr/bin/env python3
"""Execute and summarize the twenty mandatory AC-23 mutation categories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


from junit_closed_profile import parse_pytest_junit_closed
from strict_json import (
    canonical_json_bytes,
    require_exact_dict_keys,
    require_git_oid,
    strict_json_file,
)
from verify_candidate_artifact_identity import (
    MANIFEST_KEYS,
    load_evidence_policy,
    verify_mutation_results,
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _subject(package: Path) -> dict[str, str]:
    identity = package / "IDENTITY" / "candidate_artifact_identity.json"
    checksums = package / "SHA256SUMS.txt"
    value = strict_json_file(identity, max_bytes=1 << 20, require_canonical=True)
    require_exact_dict_keys(value, MANIFEST_KEYS)
    require_git_oid(value["head_commit"])
    require_git_oid(value["head_tree"])
    return {
        "subject_checksum_sha256": _sha256(checksums),
        "subject_identity_sha256": _sha256(identity),
        "subject_head_commit": value["head_commit"],
        "subject_head_tree": value["head_tree"],
    }


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
    canonical_path = stem.with_suffix(".canonical.json")
    for path in (output, stdout_path, stderr_path, junit_path, canonical_path):
        if path.exists():
            raise ValueError("mutation output already exists")
    run_root = repository / ".ac23-mutation-run"
    if run_root.exists() or run_root.is_symlink():
        raise ValueError("mutation run path already exists")
    run_root.mkdir()
    environment_temp = run_root / "environment-tmp"
    verifier_work = run_root / "verifier-work"
    environment_temp.mkdir(mode=0o700)
    verifier_work.mkdir(mode=0o700)
    baseline_env = {
        "PATH": os.environ.get("PATH", ""),
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": os.fspath(environment_temp),
        "TEMP": os.fspath(environment_temp),
        "TMP": os.fspath(environment_temp),
    }
    try:
        baseline = subprocess.run(
            [
                sys.executable,
                os.fspath(package / "VERIFY/verify_candidate_artifact_identity.py"),
                os.fspath(package),
                "--work-root",
                os.fspath(verifier_work),
            ],
            cwd=run_root,
            env=baseline_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if baseline.returncode != 0 or not baseline.stdout.rstrip().endswith(b"AC23_PASS=YES"):
            raise RuntimeError("subject package is not a valid AC-23 package")
        subject = _subject(package)
    except Exception:
        shutil.rmtree(run_root)
        raise
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
            "tests/ac23/test_verifier_purity.py",
            "-k",
            "mutation or evidence_semantics_attack or closed_junit_integration_attack",
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
            "TMPDIR": os.fspath(environment_temp),
            "TEMP": os.fspath(environment_temp),
            "TMP": os.fspath(environment_temp),
        }
        completed = subprocess.run(argv, cwd=repository, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if raw_junit.is_file():
            junit_path.write_bytes(raw_junit.read_bytes())
    finally:
        shutil.rmtree(run_root)
        if run_root.exists() or run_root.is_symlink():
            raise RuntimeError("mutation work root cleanup failed")
    end = _utc()
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    if completed.returncode != 0 or not junit_path.is_file():
        raise RuntimeError("mutation pytest failed")
    expected = {
        testcase
        for item in policy["legacy_mutation_categories"]
        for testcase in item["testcases"]
    } | {item["testcase"] for item in policy["evidence_semantic_categories"]} | {
        item["testcase"] for item in policy["junit_profile"]["closed_junit_cases"]
    }
    limits = policy["limits"]
    canonical = parse_pytest_junit_closed(
        junit_path.read_bytes(),
        expected_testcase_ids=frozenset(expected),
        max_bytes=limits["max_junit_bytes"],
        max_elements=limits["max_xml_elements"],
        max_testcases_per_run=limits["max_testcases_per_run"],
        max_attribute_count_per_element=limits["max_attribute_count_per_element"],
        max_attribute_value_bytes=limits["max_attribute_value_bytes"],
        max_testcase_id_bytes=limits["max_testcase_id_bytes"],
    )
    canonical_path.write_bytes(canonical.to_bytes())
    legacy = policy["legacy_mutation_categories"]
    semantic = policy["evidence_semantic_categories"]
    closed = policy["junit_profile"]["closed_junit_cases"]
    result = {
        "schema_version": "butler.box5.ac23-mutation-results.v3",
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
            "tests/ac23/test_verifier_purity.py",
            "-k",
            "mutation or evidence_semantics_attack or closed_junit_integration_attack",
            "--junitxml=.ac23-mutation-run/results.xml",
            "--basetemp",
            ".ac23-mutation-run/tmp",
        ],
        "cwd": "candidate",
        "exit_code": completed.returncode,
        "termination": "exit",
        **subject,
        "legacy_categories": [
            {**item, "status": "PASS"}
            for item in legacy
        ],
        "evidence_semantic_categories": [
            {**item, "status": "PASS"}
            for item in semantic
        ],
        "closed_junit_cases": [
            {**item, "status": "PASS"}
            for item in closed
        ],
        "stdout_path": "mutation/pytest_mutation.stdout.bin",
        "stdout_sha256": _sha256(stdout_path),
        "stderr_path": "mutation/pytest_mutation.stderr.bin",
        "stderr_sha256": _sha256(stderr_path),
        "junit_path": "mutation/pytest_mutation.xml",
        "junit_sha256": _sha256(junit_path),
        "canonical_path": "mutation/canonical.json",
        "canonical_sha256": _sha256(canonical_path),
        "summary": {
            "failed": 0,
            "legacy_categories_passed": len(legacy),
            "legacy_subcases_passed": sum(len(item["testcases"]) for item in legacy),
            "existing_semantic_categories_passed": len(semantic),
            "closed_junit_categories_passed": len({item["category"] for item in closed}),
            "closed_junit_subcases_passed": len(closed),
        },
    }
    output.write_bytes(canonical_json_bytes(result))
    if _subject(package) != subject:
        raise RuntimeError("subject package changed during mutation tests")
    verify_mutation_results(
        {
            "mutation/mutation_results_v3.json": output.read_bytes(),
            "mutation/pytest_mutation.stdout.bin": stdout_path.read_bytes(),
            "mutation/pytest_mutation.stderr.bin": stderr_path.read_bytes(),
            "mutation/pytest_mutation.xml": junit_path.read_bytes(),
            "mutation/canonical.json": canonical_path.read_bytes(),
        },
        policy,
        expected_subject=subject,
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
        default=Path(__file__).with_name("evidence_policy_v3.json"),
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
