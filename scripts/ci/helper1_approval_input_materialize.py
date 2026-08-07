#!/usr/bin/env python3
"""Materialize a verified approval artifact for GitHub artifact re-publication."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_input import provenance_from_dict, verify_approval_input_bytes  # noqa: E402
from butler_pc_core.helper1.failure_codes import Helper1V61Error  # noqa: E402


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
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        provenance_value = json.loads(args.provenance.read_bytes())
        if not isinstance(provenance_value, dict):
            raise ValueError
        verified = verify_approval_input_bytes(
            args.artifact.read_bytes(),
            provenance_from_dict(provenance_value),
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
        args.output_root.mkdir(parents=True, mode=0o700)
        for name, raw in sorted(verified.files.items()):
            target = args.output_root.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                os.close(descriptor)
    except Helper1V61Error as exc:
        print("HELPER1_APPROVAL_INPUT_MATERIALIZE_OK=0")
        print(f"ERROR_CODE={exc.code.value}")
        return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print("HELPER1_APPROVAL_INPUT_MATERIALIZE_OK=0")
        print("ERROR_CODE=NO_EXPLICIT_PRODUCER")
        return 1
    print("HELPER1_APPROVAL_INPUT_MATERIALIZE_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
