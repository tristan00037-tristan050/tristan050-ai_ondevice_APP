#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REQUIRED_FUNCTIONS = {"dialogue", "summarize", "retrieval_transform", "policy_sensitive"}
VALID_SPLITS = {"train", "validation", "test"}


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify AIHub preprocess output")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        print("AIHUB_LOAD_OK=0")
        sys.exit(1)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ok = summary.get("AIHUB_LOAD_OK") == 1
    split_counts = {name: count_jsonl(out_dir / f"{name}.jsonl") for name in VALID_SPLITS}
    functions = set(summary.get("detected_functions", []))
    functions_ok = REQUIRED_FUNCTIONS.issubset(functions)
    splits_ok = all(name in split_counts for name in VALID_SPLITS)
    nonzero_ok = split_counts["train"] > 0 and split_counts["validation"] > 0 and split_counts["test"] > 0
    print(f"AIHUB_LOAD_OK={1 if ok else 0}")
    print(f"AIHUB_FUNCTION_COVERAGE_OK={1 if functions_ok else 0}")
    print(f"AIHUB_SPLITS_OK={1 if splits_ok else 0}")
    print(f"AIHUB_NONZERO_SPLITS_OK={1 if nonzero_ok else 0}")
    if not (ok and functions_ok and splits_ok and nonzero_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
