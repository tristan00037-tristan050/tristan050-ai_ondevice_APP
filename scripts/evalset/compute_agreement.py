#!/usr/bin/env python3
"""compute_agreement.py — 단계 6.5.5 Day 1 CI Gate #5.

같은 sample_id 에 대해 2인 라벨링 결과의 합의도를 계산.

입력 : JSONL — 각 line 에 (sample_id, intent_type, deadline_type, auto_apply_allowed,
                          annotator_id) 등 라벨이 들어있다.
출력 : intent / deadline / auto_apply 일치율 + 합의도 기준 PASS/FAIL.

기준 (CARD1_EVALSET_SPEC §6):
- intent ≥ 0.85
- deadline ≥ 0.80
- auto_apply ≥ 0.95
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

THRESHOLDS = {
    "intent_type":        0.85,
    "deadline_type":      0.80,
    "auto_apply_allowed": 0.95,
}


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

    by_sample: Dict[str, List[dict]] = defaultdict(list)
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
            sid = item.get("sample_id")
            if sid:
                by_sample[sid].append(item)
                total += 1

    paired = {sid: items for sid, items in by_sample.items() if len(items) >= 2}

    agreement: Dict[str, dict] = {}
    for field in THRESHOLDS:
        match = 0
        n     = 0
        for sid, items in paired.items():
            a, b = items[0].get(field), items[1].get(field)
            if a is None or b is None:
                continue
            n += 1
            if a == b:
                match += 1
        rate = (match / n) if n > 0 else 1.0
        agreement[field] = {
            "rate":      round(rate, 4),
            "matches":   match,
            "n":         n,
            "threshold": THRESHOLDS[field],
            "passed":    rate >= THRESHOLDS[field],
        }

    ok = all(v["passed"] for v in agreement.values())
    report = {
        "ok":               ok,
        "fail_class":       "AGREEMENT_BELOW_THRESHOLD" if not ok else None,
        "total_labels":     total,
        "paired_samples":   len(paired),
        "agreement":        agreement,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
