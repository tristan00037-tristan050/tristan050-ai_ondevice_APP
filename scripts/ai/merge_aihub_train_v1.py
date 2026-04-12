from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import jsonl_read, jsonl_write, REQUIRED_FIELDS

INPUT_NAMES = [
    "tool_call_nl2sql.jsonl",
    "rewrite_office.jsonl",
    "retrieval_event.jsonl",
    "dialogue_merged.jsonl",
    "domain_merged.jsonl",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    all_rows = []
    counts = {}
    source_counts = Counter()
    function_counts = Counter()
    split_counts = Counter()
    seen = set()
    dup_removed = 0
    raw_line_count = 0
    for name in INPUT_NAMES:
        rows = jsonl_read(Path(args.input_dir) / name)
        counts[name] = len(rows)
        raw_line_count += len(rows)
        for row in rows:
            key = row.get("prompt", "")
            if key in seen:
                dup_removed += 1
                continue
            seen.add(key)
            all_rows.append(row)
            source_counts[row.get("source", "unknown")] += 1
            function_counts[row.get("function", "unknown")] += 1
            split_counts[row.get("split", "unknown")] += 1
    total = jsonl_write(args.output, all_rows)
    manifest = {
        "input_files": counts,
        "raw_line_count": raw_line_count,
        "dedup_removed": dup_removed,
        "final_line_count": total,
        "function_counts": dict(function_counts),
        "source_counts": dict(source_counts),
        "validation_split_counts": dict(split_counts),
        "required_fields": REQUIRED_FIELDS,
    }
    mpath = Path(args.output).with_name("merge_manifest.json")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("AIHUB_MERGE_OK=1")
    print(f"AIHUB_TOTAL_COUNT={total}")


if __name__ == "__main__":
    main()
