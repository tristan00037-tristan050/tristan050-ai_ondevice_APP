#!/usr/bin/env python3
"""Execute and summarize the twenty mandatory AC-23 mutation categories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CATEGORIES = set(range(1, 21))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _category(name: str) -> int:
    direct = re.search(r"test_mutation_(\d{2})(?:_|\[|$)", name)
    if direct and direct.group(1) != "06":
        return int(direct.group(1))
    if "test_mutation_06_to_09_raw_digest" in name:
        mapping = {
            "E_PATCH_DIGEST": 6,
            "E_SOURCE_DIGEST": 7,
            "E_CHANGED_PATH_DIGEST": 8,
            "E_EVIDENCE_DIGEST": 9,
        }
        for marker, value in mapping.items():
            if marker in name:
                return value
    raise ValueError(f"unmapped mutation testcase: {name}")


def run(args: argparse.Namespace) -> Path:
    repository = args.repo.resolve()
    package = args.package.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stem = output.with_suffix("")
    stdout_path = stem.with_suffix(".stdout.bin")
    stderr_path = stem.with_suffix(".stderr.bin")
    junit_path = stem.with_suffix(".xml")
    for path in (output, stdout_path, stderr_path, junit_path):
        if path.exists():
            raise ValueError("mutation output already exists")
    start = _utc()
    with tempfile.TemporaryDirectory(prefix="ac23-mutation-tmp-") as pytest_tmp:
        argv = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "tests/ac23/test_candidate_artifact_identity.py",
            "-k",
            "mutation",
            f"--junitxml={junit_path}",
            "--basetemp",
            pytest_tmp,
        ]
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AC23_PACKAGE_ROOT": os.fspath(package),
            "BUTLER_APP_DATA_DIR": os.fspath(Path(pytest_tmp) / "app-data"),
        }
        completed = subprocess.run(
            argv,
            cwd=repository,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    end = _utc()
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    if completed.returncode != 0 or not junit_path.is_file():
        raise RuntimeError("mutation pytest failed")
    tree = ET.parse(junit_path)
    categories: dict[int, list[str]] = {}
    for testcase in tree.findall(".//testcase"):
        name = testcase.attrib.get("name", "")
        if "test_mutation_" not in name:
            continue
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            raise RuntimeError("mutation testcase failed")
        categories.setdefault(_category(name), []).append(name)
    if set(categories) != EXPECTED_CATEGORIES:
        raise RuntimeError("mutation category coverage mismatch")
    result = {
        "schema_version": "butler.box5.ac23-mutation-results.v1",
        "start_utc": start,
        "end_utc": end,
        "argv": [
            "python3",
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "tests/ac23/test_candidate_artifact_identity.py",
            "-k",
            "mutation",
        ],
        "cwd": "candidate",
        "exit_code": completed.returncode,
        "categories": [
            {
                "category": number,
                "case_count": len(categories[number]),
                "status": "PASS",
            }
            for number in sorted(categories)
        ],
        "subcase_total": sum(len(values) for values in categories.values()),
        "stdout_sha256": _sha256(stdout_path),
        "stderr_sha256": _sha256(stderr_path),
        "junit_sha256": _sha256(junit_path),
        "summary": {"failed": 0, "passed": 20, "total": 20},
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
