#!/usr/bin/env python3
"""validate_card1_schema.py — 단계 6.5.5 Day 1 CI Gate #6.

JSONL EvalSet 의 각 sample 을 schemas/card1_eval_item.schema.json 으로 검증.

PASS: exit 0
FAIL: exit 1, fail_class=SCHEMA_INVALID + errors[:50]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",  required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--out",    default=None)
    args = p.parse_args()

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print(json.dumps({
            "ok": False, "fail_class": "JSONSCHEMA_NOT_INSTALLED",
            "hint": "pip install jsonschema",
        }, ensure_ascii=False))
        return 1

    in_path     = Path(args.input)
    schema_path = Path(args.schema)
    if not in_path.exists() or not schema_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "input": str(in_path), "schema": str(schema_path)},
                         ensure_ascii=False))
        return 1

    schema    = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors: List[dict] = []
    total = 0
    with in_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append({"line_no": line_no, "fail_class": "JSON_DECODE",
                               "detail": str(e)})
                continue
            for err in validator.iter_errors(item):
                errors.append({
                    "line_no":   line_no,
                    "sample_id": item.get("sample_id", "unknown"),
                    "path":      list(err.absolute_path),
                    "message":   err.message,
                })

    ok = len(errors) == 0
    report = {
        "ok":           ok,
        "fail_class":   "SCHEMA_INVALID" if not ok else None,
        "total_items":  total,
        "error_count":  len(errors),
        "errors":       errors[:50],
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
