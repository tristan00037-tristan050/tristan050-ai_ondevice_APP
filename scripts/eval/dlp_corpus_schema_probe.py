#!/usr/bin/env python3
"""Digest-only schema probe for an external JSONL DLP mutation corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "butler.dlp_corpus_schema_probe.v1"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def probe(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    keys: set[str] = set()
    types: Counter[str] = Counter()
    rows = 0
    invalid_rows = 0
    for line in data.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid_rows += 1
            continue
        if not isinstance(row, dict):
            invalid_rows += 1
            continue
        rows += 1
        keys.update(str(key) for key in row)
        for key, value in row.items():
            types[f"{key}:{_type_name(value)}"] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        "row_count": rows,
        "invalid_row_count": invalid_rows,
        "top_level_keys": sorted(keys),
        "type_histogram": dict(sorted(types.items())),
        "raw_text_logged": False,
        "external_send_zero": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = probe(args.corpus)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if result["invalid_row_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
