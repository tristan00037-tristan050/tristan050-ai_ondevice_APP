#!/usr/bin/env python3
"""
verify_cross_split_duplicate_v1.py — cross-split leakage 검증 (fail-closed, machine-readable only)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def pair_digest(prompt: str, completion: str) -> str:
    payload = json.dumps({"prompt": prompt, "completion": completion}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def norm_text(s: str) -> str:
    return " ".join(s.split())


def load_pairs(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        raise RuntimeError(f"SPLIT_FILE_MISSING:{path.name}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"SPLIT_FILE_EMPTY:{path.name}")

    pairs: set[tuple[str, str]] = set()
    nonblank = 0
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        nonblank += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"SPLIT_JSON_INVALID:{path.name}:{i}:{e.msg}") from e
        if not isinstance(row, dict):
            raise RuntimeError(f"SPLIT_RECORD_NOT_OBJECT:{path.name}:{i}")
        if "prompt" not in row or "completion" not in row:
            raise RuntimeError(f"SPLIT_RECORD_FIELD_MISSING:{path.name}:{i}")
        raw_p = row["prompt"]
        raw_c = row["completion"]
        if not isinstance(raw_p, str):
            raise RuntimeError(f"SPLIT_RECORD_PROMPT_NOT_STRING:{path.name}:{i}:{type(raw_p).__name__}")
        if not isinstance(raw_c, str):
            raise RuntimeError(f"SPLIT_RECORD_COMPLETION_NOT_STRING:{path.name}:{i}:{type(raw_c).__name__}")
        p = norm_text(raw_p)
        c = norm_text(raw_c)
        if not p or not c:
            raise RuntimeError(f"SPLIT_RECORD_NORM_EMPTY:{path.name}:{i}")
        pairs.add((p, c))

    if nonblank == 0:
        raise RuntimeError(f"SPLIT_FILE_WHITESPACE_ONLY:{path.name}")

    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="cross-split (prompt, completion) 중복 검증")
    ap.add_argument("--data-dir", default=None, help="train/validation/test.jsonl 디렉터리")
    args = ap.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir).resolve()
    else:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_v40"

    splits = ["train", "validation", "test"]
    split_pairs: dict[str, set[tuple[str, str]]] = {}

    try:
        for split in splits:
            path = data_dir / f"{split}.jsonl"
            split_pairs[split] = load_pairs(path)
            print(f"{split.upper()}_PAIR_COUNT={len(split_pairs[split])}")

        print("CROSS_SPLIT_REQUIRED_FILES_PRESENT_OK=1")
        print("CROSS_SPLIT_NONEMPTY_CONTENT_REQUIRED_OK=1")
        print("CROSS_SPLIT_RECORD_STRING_FIELDS_REQUIRED_OK=1")

        pairs_check = [
            ("train", "validation"),
            ("train", "test"),
            ("validation", "test"),
        ]
        for a, b in pairs_check:
            overlap = split_pairs[a] & split_pairs[b]
            if overlap:
                digests = sorted(pair_digest(p, c) for p, c in overlap)
                print("ERROR_CODE=CROSS_SPLIT_DUPLICATE_OVERLAP", file=sys.stderr)
                print(f"OVERLAP_PAIR_COUNT={len(overlap)}", file=sys.stderr)
                print(f"SPLIT_A={a}", file=sys.stderr)
                print(f"SPLIT_B={b}", file=sys.stderr)
                print(f"FIRST_OVERLAP_PAIR_DIGEST={digests[0]}", file=sys.stderr)
                print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=0")
                print("CROSS_SPLIT_DUPLICATE_NO_RAW_LOG_OK=1")
                return 1

        print("CROSS_SPLIT_DUPLICATE_NO_RAW_LOG_OK=1")
        print("CROSS_SPLIT_DUPLICATE_SIGNAL_SINGLE_SOURCE_OK=1")
        print("VERIFY_OUTPUT_MACHINE_READABLE_ONLY_OK=1")
        print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1")
        return 0

    except RuntimeError as e:
        print(f"ERROR_CODE={e}", file=sys.stderr)
        print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=0")
        print("CROSS_SPLIT_DUPLICATE_SIGNAL_SINGLE_SOURCE_OK=1")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
