#!/usr/bin/env python3
"""Verify a fetched Helper1 approval artifact without executing its contents."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_input import (  # noqa: E402
    provenance_from_dict,
    verify_approval_input_bytes,
)
from butler_pc_core.helper1.failure_codes import Helper1V61Error  # noqa: E402

MAX_ARTIFACT_BYTES = 160 * 1024 * 1024
MAX_PROVENANCE_BYTES = 64 * 1024


def _read_regular(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise OSError
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            raw = handle.read(limit + 1)
    finally:
        os.close(descriptor)
    if len(raw) > limit:
        raise OSError
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--subject-tree", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-id", required=True, type=int)
    parser.add_argument("--workflow-sha256", required=True)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--canonical-subject-sha256", required=True)
    args = parser.parse_args()
    try:
        artifact = _read_regular(args.artifact, MAX_ARTIFACT_BYTES)
        provenance_raw = _read_regular(args.provenance, MAX_PROVENANCE_BYTES)
        value = json.loads(
            provenance_raw,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if not isinstance(value, dict):
            raise ValueError
        provenance = provenance_from_dict(value)
        verify_approval_input_bytes(
            artifact,
            provenance,
            expected_repository_id=args.repository_id,
            expected_repository_name=args.repository,
            expected_subject_commit=args.subject_commit,
            expected_subject_tree=args.subject_tree,
            expected_run_id=args.run_id,
            expected_run_attempt=args.run_attempt,
            expected_workflow_ref=args.workflow_ref,
            expected_workflow_id=args.workflow_id,
            expected_workflow_sha256=args.workflow_sha256,
            expected_artifact_id=args.artifact_id,
            expected_artifact_name=args.artifact_name,
            expected_canonical_subject_sha256=args.canonical_subject_sha256,
        )
    except Helper1V61Error as exc:
        print("HELPER1_APPROVAL_INPUT_VERIFY_OK=0")
        print(f"ERROR_CODE={exc.code.value}")
        return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print("HELPER1_APPROVAL_INPUT_VERIFY_OK=0")
        print("ERROR_CODE=NO_EXPLICIT_PRODUCER")
        return 1
    print("HELPER1_APPROVAL_INPUT_VERIFY_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
