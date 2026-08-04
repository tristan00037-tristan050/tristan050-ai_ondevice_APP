#!/usr/bin/env python3
"""Run every v5.1 evidence lane/check and write one canonical index."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.canonical_json import canonicalize_butler_cj1  # noqa: E402
from butler_pc_core.helper1.test_evidence import (  # noqa: E402
    CHECKS,
    LANES,
    TestEvidenceError,
    build_evidence_index,
    run_check,
    run_test_lane,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args()
    if args.index.exists() or args.index.is_symlink():
        print("HELPER1_V51_EVIDENCE_OK=0")
        print("ERROR_CODE=EVIDENCE_INDEX_ALREADY_EXISTS")
        return 1
    try:
        lanes = tuple(run_test_lane(lane_id, args.output_root) for lane_id in sorted(LANES))
        checks = tuple(run_check(check_id, args.output_root) for check_id in sorted(CHECKS))
        index = build_evidence_index(lanes, checks)
        args.index.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = args.index.with_suffix(args.index.suffix + ".tmp")
        temporary.write_bytes(canonicalize_butler_cj1(index))
        os.replace(temporary, args.index)
    except (OSError, TestEvidenceError):
        print("HELPER1_V51_EVIDENCE_OK=0")
        print("ERROR_CODE=EVIDENCE_COLLECTION_FAILED")
        return 1
    required_pass = bool(index["all_required_lanes_passed"] and index["all_required_checks_passed"])
    print(f"HELPER1_V51_EVIDENCE_OK={int(required_pass)}")
    print(f"REQUIRED_LANES_BLOCKED={index['required_lanes_blocked']}")
    print("ERROR_CODE=NONE" if required_pass else "ERROR_CODE=REQUIRED_LANE_BLOCKED")
    return 0 if required_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
