#!/usr/bin/env python3
"""check_digest16.py — 단계 6.5.5 Day 1 CI Gate #2.

raw_digest16 형식이 `^sha256:[0-9a-f]{16}$` 인지 검사.

PASS: exit 0, 보고서 ok=true
FAIL: exit 1, fail_class=DIGEST16_INVALID + 위반 sample_id 목록
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List

DIGEST16_RE = re.compile(r"^sha256:[0-9a-f]{16}$")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out",   default=None)
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
                violations.append({"line_no": line_no, "detail": str(e),
                                   "fail_class": "JSON_DECODE"})
                continue
            digest = item.get("raw_digest16")
            if not isinstance(digest, str) or not DIGEST16_RE.match(digest):
                violations.append({
                    "line_no":   line_no,
                    "sample_id": item.get("sample_id", "unknown"),
                    "digest":    digest,
                })

    ok = len(violations) == 0
    report = {
        "ok":             ok,
        "fail_class":     "DIGEST16_INVALID" if not ok else None,
        "total_items":    total,
        "invalid_digest": len(violations),
        "violations":     violations[:50],
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
