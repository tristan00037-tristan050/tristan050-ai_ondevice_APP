#!/usr/bin/env python3
"""
collect_data_impl_v1.py — fail-closed 수집기
- strict JSONL 로더: malformed 한 줄이라도 즉시 RuntimeError
- non-empty 3분할 보장: n < 3 → BLOCK, n >= 3 → train/validation/test 각 최소 1건
- 출력: COLLECT_DATA_JSONL_STRICT_PARSE_OK=1, DATASET_SPLIT_NONEMPTY_V1_OK=1 등 key=value만
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def load_jsonl_records_strict(path: Path, source_name: str) -> list[dict]:
    """JSONL 파일을 엄격히 로드. 파싱 실패 시 즉시 RuntimeError."""
    records: list[dict] = []
    if not path.exists():
        return records
    raw_text = path.read_text(encoding="utf-8")
    for i, raw_line in enumerate(raw_text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"{source_name.upper()}_JSON_INVALID:{path.name}:{i}:{e.msg}"
            ) from e
        if not isinstance(row, dict):
            raise RuntimeError(
                f"{source_name.upper()}_ROW_NOT_OBJECT:{path.name}:{i}"
            )
        records.append(row)
    return records


def compute_nonempty_split_counts(n: int) -> dict[str, int]:
    """n >= 3일 때 train/validation/test 각 최소 1건 보장. n < 3이면 RuntimeError."""
    if n < 3:
        raise RuntimeError(f"SPLIT_COUNT_TOO_SMALL:{n}")
    counts = {"train": 1, "validation": 1, "test": 1}
    remaining = n - 3
    weights = {"train": 0.8, "validation": 0.1, "test": 0.1}
    raw = {k: remaining * weights[k] for k in counts}
    for k in counts:
        counts[k] += int(raw[k])
    assigned = sum(counts.values())
    leftover = n - assigned
    order = sorted(
        counts.keys(),
        key=lambda k: (raw[k] - int(raw[k]), weights[k]),
        reverse=True,
    )
    for k in order[:leftover]:
        counts[k] += 1
    return counts


def hash_record(rec: dict) -> str:
    return hashlib.sha256(
        json.dumps(rec, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def dedupe(records: list[dict], digest_key: str = "record_digest_sha256") -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for rec in records:
        d = rec.get(digest_key) or hash_record(rec)
        if d in seen:
            continue
        seen.add(d)
        if digest_key not in rec:
            rec = {**rec, digest_key: d}
        out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fail-closed JSONL merge + non-empty split")
    ap.add_argument("--wiki", type=Path, default=None, help="wiki JSONL path")
    ap.add_argument("--dialogue", type=Path, default=None, help="dialogue JSONL path")
    ap.add_argument("--out-dir", type=Path, default=Path("data/collected"), help="Output dir for train/validation/test.jsonl")
    ap.add_argument("--min-text-len", type=int, default=100, help="Min text length for wiki rows")
    args = ap.parse_args()

    all_records: list[dict] = []

    if args.wiki and args.wiki.exists() and args.wiki.stat().st_size > 0:
        wiki_rows = load_jsonl_records_strict(args.wiki, "wiki")
        for item in wiki_rows:
            text = (item.get("text") or "").strip()
            if len(text) < args.min_text_len:
                continue
            prompt = text[:500]
            completion = text[500:5000] if len(text) > 500 else text
            rec = {
                "prompt": prompt,
                "completion": completion,
                "source": "wiki",
                "record_digest_sha256": "",
            }
            rec["record_digest_sha256"] = hash_record(rec)
            all_records.append(rec)

    if args.dialogue and args.dialogue.exists() and args.dialogue.stat().st_size > 0:
        dialogue_rows = load_jsonl_records_strict(args.dialogue, "dialogue")
        for item in dialogue_rows:
            if not item.get("prompt") or not item.get("completion"):
                continue
            rec = {
                "prompt": str(item.get("prompt", "")).strip(),
                "completion": str(item.get("completion", "")).strip(),
                "source": "dialogue",
                "record_digest_sha256": "",
            }
            rec["record_digest_sha256"] = hash_record(rec)
            all_records.append(rec)

    all_records = dedupe(all_records)
    n = len(all_records)
    split_counts = compute_nonempty_split_counts(n)
    train_n = split_counts["train"]
    val_n = split_counts["validation"]
    test_n = split_counts["test"]

    splits = {
        "train": all_records[:train_n],
        "validation": all_records[train_n : train_n + val_n],
        "test": all_records[train_n + val_n : train_n + val_n + test_n],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for split_name, rows in splits.items():
        path = args.out_dir / f"{split_name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("COLLECT_DATA_JSONL_STRICT_PARSE_OK=1")
    print("DATASET_SPLIT_NONEMPTY_V1_OK=1")
    print("COLLECT_DATA_BLOCKS_ON_TOO_SMALL_SPLIT_INPUT_OK=1")
    print(f"TRAIN_PAIR_COUNT={len(splits['train'])}")
    print(f"VALIDATION_PAIR_COUNT={len(splits['validation'])}")
    print(f"TEST_PAIR_COUNT={len(splits['test'])}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"ERROR_CODE={e}", file=sys.stderr)
        sys.exit(1)
