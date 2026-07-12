#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _typename(value: object) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    keys: set[str] = set()
    types: Counter[str] = Counter()
    rows = 0
    try:
        data = args.corpus.read_bytes()
        for line in data.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("CORPUS_ROW_NOT_OBJECT")
            rows += 1
            keys.update(str(key) for key in row)
            for key, value in row.items():
                types[f"{key}:{_typename(value)}"] += 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        print("DLP_CORPUS_SCHEMA_PROBE_OK=0")
        print("ERROR_CODE=CORPUS_SCHEMA_UNKNOWN")
        return 1

    print("DLP_CORPUS_SCHEMA_PROBE_OK=1")
    print(
        json.dumps(
            {
                "schema_version": "butler.dlp_corpus_schema_probe.v1",
                "corpus_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "row_count": rows,
                "top_level_keys": sorted(keys),
                "type_histogram": dict(sorted(types.items())),
                "raw_text_logged": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
