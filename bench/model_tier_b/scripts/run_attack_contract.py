#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))

from test_attack_matrix_v28 import MATRIX_ROWS, run_case  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    for case_id in sorted(MATRIX_ROWS):
        exit_code, fail_class = run_case(case_id); row = MATRIX_ROWS[case_id]
        passed = exit_code != 0 and fail_class == row["expected_fail_class"]
        results.append({"attack_id": case_id, "name": row["name"], "expected_fail_class": row["expected_fail_class"], "observed_exit": exit_code, "observed_fail_class": fail_class, "expected_block": passed})
    report = {"schema_version": "butler.model-tier-b.attack-results.v2.8", "total": len(results), "expected_block_count": sum(item["expected_block"] for item in results), "unexpected_count": sum(not item["expected_block"] for item in results), "results": results}
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["unexpected_count"] == 0 else 12


if __name__ == "__main__":
    raise SystemExit(main())
