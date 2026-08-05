#!/usr/bin/env python3
"""Seal the exact SearchQuality stage outputs into one manifest."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.quality_evidence import (  # noqa: E402
    MANIFEST_NAME,
    QUALITY_FILES,
    QualityEvidenceError,
    build_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--evaluation-run-id", required=True)
    parser.add_argument("--evaluation-run-attempt", required=True, type=int)
    parser.add_argument("--producer-run-id", required=True)
    parser.add_argument("--producer-run-attempt", required=True, type=int)
    parser.add_argument("--workflow-id", required=True, type=int)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha256", required=True)
    args = parser.parse_args()
    try:
        files = {name: (args.root / name).read_bytes() for name in QUALITY_FILES}
        raw = build_manifest(
            files,
            source_commit=args.source_commit,
            source_tree=args.source_tree,
            evaluation_run_id=args.evaluation_run_id,
            evaluation_run_attempt=args.evaluation_run_attempt,
            producer_run_id=args.producer_run_id,
            producer_run_attempt=args.producer_run_attempt,
            workflow_id=args.workflow_id,
            workflow_ref=args.workflow_ref,
            workflow_sha256=args.workflow_sha256,
        )
        output = args.root / MANIFEST_NAME
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, QualityEvidenceError):
        print("HELPER1_QUALITY_MANIFEST_OK=0")
        print("ERROR_CODE=QUALITY_INVENTORY_INVALID")
        return 1
    print("HELPER1_QUALITY_MANIFEST_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
