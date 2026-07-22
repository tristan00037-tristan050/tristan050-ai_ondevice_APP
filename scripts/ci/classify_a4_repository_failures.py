#!/usr/bin/env python3
"""Classify repository-wide pytest failures without treating them as passes."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


SCHEMA_VERSION = "butler.box5.a4.repository_failure_classification.v5.5"
A4_TEST_PREFIXES = (
    "tests.accounting.classify.test_a4_",
    "tests.accounting.classify.swift.",
)


def failed_nodeids(junit_path: Path) -> tuple[str, ...]:
    root = ET.parse(junit_path).getroot()
    failures: set[str] = set()
    for testcase in root.iter("testcase"):
        if testcase.find("failure") is None and testcase.find("error") is None:
            continue
        classname = testcase.get("classname")
        name = testcase.get("name")
        if not classname or not name:
            raise ValueError("JUnit testcase identity is incomplete")
        failures.add(f"{classname}::{name}")
    return tuple(sorted(failures))


def _load_baselines(
    baseline_path: Path, overlay_paths: Sequence[Path]
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    expected: dict[str, str] = {}
    owners: dict[str, str] = {}
    sources: list[str] = []
    paths = (baseline_path, *overlay_paths)
    for index, path in enumerate(paths):
        baseline = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(baseline, dict)
            or baseline.get("schema_version")
            != "butler.box5.a4.repository_failure_baseline.v5.5"
            or not isinstance(baseline.get("failures"), dict)
            or not isinstance(baseline.get("owner_notes"), dict)
        ):
            raise ValueError("failure baseline is invalid")
        if index and baseline.get("baseline_role") != "platform_overlay":
            raise ValueError("failure baseline overlay role is invalid")
        incoming: dict[str, str] = baseline["failures"]
        incoming_owners: dict[str, str] = baseline["owner_notes"]
        if not incoming or any(owner not in incoming_owners for owner in incoming.values()):
            raise ValueError("failure baseline ownership is incomplete")
        overlap = set(expected) & set(incoming)
        if overlap:
            raise ValueError("failure baselines contain duplicate nodeids")
        owner_conflicts = {
            owner
            for owner, note in incoming_owners.items()
            if owner in owners and owners[owner] != note
        }
        if owner_conflicts:
            raise ValueError("failure baseline owner notes conflict")
        expected.update(incoming)
        owners.update(incoming_owners)
        sources.append(path.name)
    return expected, owners, sources


def classify(
    *,
    junit_path: Path,
    baseline_path: Path,
    pytest_exit_code: int,
    overlay_paths: Sequence[Path] = (),
) -> dict[str, object]:
    if pytest_exit_code not in {0, 1}:
        raise ValueError("pytest did not complete normally")
    expected, _owners, sources = _load_baselines(baseline_path, overlay_paths)
    observed = set(failed_nodeids(junit_path))
    unknown = sorted(observed - set(expected))
    a4_owned = sorted(
        nodeid for nodeid in observed if nodeid.startswith(A4_TEST_PREFIXES)
    )
    external = [
        {"nodeid": nodeid, "owner_track": expected[nodeid]}
        for nodeid in sorted(observed & set(expected))
    ]
    resolved = sorted(set(expected) - observed)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS_WITH_CLASSIFIED_EXTERNAL_FAILURES"
        if not unknown and not a4_owned
        else "BLOCKED",
        "pytest_exit_code": pytest_exit_code,
        "raw_failure_output_included": False,
        "baseline_sources": sources,
        "baseline_failure_count": len(expected),
        "observed_failure_count": len(observed),
        "a4_owned_failure_count": len(a4_owned),
        "unknown_failure_count": len(unknown),
        "classified_external_failures": external,
        "resolved_baseline_nodeids": resolved,
        "a4_owned_failure_nodeids": a4_owned,
        "unknown_failure_nodeids": unknown,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-overlay", type=Path, action="append", default=[])
    parser.add_argument("--pytest-exit-code", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = classify(
            junit_path=args.junit,
            baseline_path=args.baseline,
            pytest_exit_code=args.pytest_exit_code,
            overlay_paths=args.baseline_overlay,
        )
    except Exception:
        print("A4_REPOSITORY_FAILURE_CLASSIFICATION_OK=0")
        print("ERROR_CODE=REPOSITORY_FAILURE_CLASSIFICATION_INVALID")
        return 2
    args.report.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    ok = report["status"] != "BLOCKED"
    print(f"A4_REPOSITORY_FAILURE_CLASSIFICATION_OK={1 if ok else 0}")
    print(f"A4_OWNED_REPOSITORY_FAILURES_ZERO={1 if report['a4_owned_failure_count'] == 0 else 0}")
    print(f"UNCLASSIFIED_REPOSITORY_FAILURES_ZERO={1 if report['unknown_failure_count'] == 0 else 0}")
    print(f"METRIC_OBSERVED_FAILURES={report['observed_failure_count']}")
    print(f"METRIC_CLASSIFIED_EXTERNAL_FAILURES={len(report['classified_external_failures'])}")
    if not ok:
        print("ERROR_CODE=REPOSITORY_FAILURE_OWNERSHIP_GATE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
