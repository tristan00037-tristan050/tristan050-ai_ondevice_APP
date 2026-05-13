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
    p.add_argument("--input",        required=True)
    p.add_argument("--min-total",    type=int, default=1)
    p.add_argument("--out",          default=None)
    p.add_argument("--separate-tags", action="store_true",
                   help="primary_intent 와 slice_tag 분리 집계 (Day 3 강화)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "INPUT_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1

    intent_counts:   Counter = Counter()
    deadline_counts: Counter = Counter()
    source_counts:   Counter = Counter()
    slice_tag_counts: Counter = Counter()
    label_status_counts: Counter = Counter()
    parse_errors: list = []
    total = 0
    with in_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                # PR #704 P1-A 정정: JSON parse 오류 fail-closed (Day 1 P2 원칙 동일).
                parse_errors.append({"line_no": line_no, "error": str(e)})
                continue
            total += 1
            intent_counts[item.get("intent_type", "?")]     += 1
            deadline_counts[item.get("deadline_type", "?")] += 1
            source_counts[item.get("source", "?")]          += 1
            label_status_counts[item.get("label_status", "?")] += 1
            for tag in (item.get("slice_tags") or []):
                slice_tag_counts[tag] += 1

    # PR #704 P1-A 정정: parse 오류가 있으면 즉시 fail (distribution 집계 무의미).
    if parse_errors:
        report = {
            "ok":                False,
            "fail_class":        "JSON_PARSE_ERROR",
            "total_items":       total,
            "parse_error_count": len(parse_errors),
            "parse_errors":      parse_errors[:50],
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    ok = total >= args.min_total
    report = {
        "ok":                  ok,
        "fail_class":          "DISTRIBUTION_BELOW_MIN" if not ok else None,
        "total_items":         total,
        "min_total":           args.min_total,
        "intent_counts":       dict(intent_counts),
        "deadline_counts":     dict(deadline_counts),
        "source_counts":       dict(source_counts),
    }
    # Day 3 강화: primary_intent 와 slice_tag 분리 집계
    if args.separate_tags:
        report["primary_intent_counts"] = dict(intent_counts)
        report["slice_tag_counts"]      = dict(slice_tag_counts)
        report["label_status_counts"]   = dict(label_status_counts)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
