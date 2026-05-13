#!/usr/bin/env python3
"""check_distribution.py — 단계 6.5.5 Day 1 CI Gate #4.

intent_type / deadline_type 분포 집계 + 최소 샘플 수 검사.

--min-total 미만이면 fail.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",      required=True)
    p.add_argument("--min-total",  type=int, default=1)
    p.add_argument("--out",        default=None)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1

    intent_counts:   Counter = Counter()
    deadline_counts: Counter = Counter()
    source_counts:   Counter = Counter()
    total = 0
    with in_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            intent_counts[item.get("intent_type", "?")]     += 1
            deadline_counts[item.get("deadline_type", "?")] += 1
            source_counts[item.get("source", "?")]          += 1

    ok = total >= args.min_total
    report = {
        "ok":              ok,
        "fail_class":      "DISTRIBUTION_BELOW_MIN" if not ok else None,
        "total_items":     total,
        "min_total":       args.min_total,
        "intent_counts":   dict(intent_counts),
        "deadline_counts": dict(deadline_counts),
        "source_counts":   dict(source_counts),
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
