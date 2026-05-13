#!/usr/bin/env python3
"""check_no_raw_text.py — 단계 6.5.5 Day 1 CI Gate #1.

JSONL EvalSet 의 모든 sample 에 raw_text 금지 키 5종이 포함되지 않았는지 검사.

금지 키: raw_text / original_text / plain_text / user_text / source_text

PASS: exit 0, 보고서 ok=true
FAIL: exit 1, fail_class=RAW_TEXT_STORED + 위반 sample_id 목록
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, List

FORBIDDEN_KEYS = {
    "raw_text",
    "original_text",
    "plain_text",
    "user_text",
    "source_text",
}


def _walk_keys(obj: Any) -> Iterable[str]:
    """JSON 객체의 모든 key 를 재귀 순회."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="EvalSet JSONL path")
    p.add_argument("--out",   default=None,  help="report JSON path (optional)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1

    violations: List[dict] = []
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
                violations.append({
                    "line_no":   line_no,
                    "fail_class": "JSON_DECODE",
                    "detail":     str(e),
                })
                continue
            keys_present = set(_walk_keys(item))
            bad = sorted(keys_present & FORBIDDEN_KEYS)
            if bad:
                violations.append({
                    "line_no":      line_no,
                    "sample_id":    item.get("sample_id", "unknown"),
                    "forbidden":    bad,
                })

    ok = len(violations) == 0
    report = {
        "ok":               ok,
        "fail_class":       "RAW_TEXT_STORED" if not ok else None,
        "total_items":      total,
        "raw_text_stored":  len(violations),
        "violations":       violations[:50],
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
