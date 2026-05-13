#!/usr/bin/env python3
"""check_pii_leak.py — 단계 6.5.5 Day 1 CI Gate #3.

text_redacted 안에 PII 잔존 패턴(이메일/전화/IP/시크릿/카드)이 남아 있는지 검사.

PASS: exit 0, 보고서 ok=true + leak_count=0
FAIL: exit 1, fail_class=PII_LEAK + 위반 sample_id 목록
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

LEAK_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("EMAIL",     re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PHONE",     re.compile(r"(?<!\d)0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)")),
    ("SERVER_IP", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    ("SECRET",    re.compile(r"(?:sk[_-]live[_-][A-Za-z0-9]+|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})")),
    ("CARD",      re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)")),
]


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

    leaks: List[dict] = []
    leak_counts: Dict[str, int] = {name: 0 for name, _ in LEAK_PATTERNS}
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
                leaks.append({"line_no": line_no, "fail_class": "JSON_DECODE",
                              "detail": str(e)})
                continue
            text = item.get("text_redacted", "")
            if not isinstance(text, str):
                continue
            sample_leaks: Dict[str, int] = {}
            for name, regex in LEAK_PATTERNS:
                hits = regex.findall(text)
                if hits:
                    sample_leaks[name] = len(hits)
                    leak_counts[name] += len(hits)
            if sample_leaks:
                leaks.append({
                    "line_no":   line_no,
                    "sample_id": item.get("sample_id", "unknown"),
                    "leaks":     sample_leaks,
                })

    leak_total = sum(leak_counts.values())
    ok = leak_total == 0
    report = {
        "ok":           ok,
        "fail_class":   "PII_LEAK" if not ok else None,
        "total_items":  total,
        "leak_count":   leak_total,
        "leak_by_type": leak_counts,
        "violations":   leaks[:50],
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
