#!/usr/bin/env python3
"""compute_agreement.py — 단계 6.5.5 Day 1 CI Gate #5.

같은 sample_id 에 대해 2인 라벨링 결과의 합의도를 계산.

P1 정정 (2026-05-13, PR #702 리뷰):
  fail-closed 원칙. 비교 가능한 쌍이 0개이면 NO_COMPARABLE_PAIRS 로 차단.
  rate=1.0 자동 통과 금지 (이전 fail-open 버그).

기준 (CARD1_EVALSET_SPEC §6):
- intent_type        ≥ 0.85
- deadline_type      ≥ 0.80
- auto_apply_allowed ≥ 0.95
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
FIELDS = list(THRESHOLDS.keys())


def simple_agreement(items: List[dict], field: str) -> dict:
    """fail-closed 합의도 계산.

    Returns:
        {ok, rate, total_pairs, agreed_pairs, fail_class?, message?}
        ok=False 인 경우 fail_class 가 포함된다.
    """
    pairs: Dict[str, list] = defaultdict(list)
    for obj in items:
        sid = obj.get("sample_id")
        if sid is None:
            continue
        if field in obj:
            pairs[sid].append(obj[field])

    agreed = 0
    total  = 0
    for vals in pairs.values():
        if len(vals) >= 2:
            total += 1
            agreed += int(vals[0] == vals[1])

    if total == 0:
        return {
            "ok":         False,
            "rate":       None,
            "total_pairs": 0,
            "agreed_pairs": 0,
            "fail_class": "NO_COMPARABLE_PAIRS",
            "message":    f"{field}: 비교 가능한 2인 라벨 쌍이 없음",
        }

    return {
        "ok":         True,
        "rate":       round(agreed / total, 4),
        "total_pairs": total,
        "agreed_pairs": agreed,
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

    items: List[dict] = []
    with in_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                # P1 정정: JSON parse error 도 fail-closed
                print(json.dumps({"ok": False, "fail_class": "JSON_PARSE_ERROR"},
                                 ensure_ascii=False))
                return 1

    field_results: Dict[str, dict] = {}
    overall_ok = True

    for field in FIELDS:
        result = simple_agreement(items, field)
        result["threshold"] = THRESHOLDS[field]

        if not result["ok"]:
            overall_ok = False
        else:
            if result["rate"] < THRESHOLDS[field]:
                result["ok"]         = False
                result["fail_class"] = "BELOW_AGREEMENT_THRESHOLD"
                overall_ok = False

        field_results[field] = result

    report = {
        "ok":     overall_ok,
        "fields": field_results,
    }
    if not overall_ok:
        # overall fail_class: 첫 번째 실패 field 의 fail_class 를 노출
        for f, r in field_results.items():
            if not r["ok"]:
                report["fail_class"] = r["fail_class"]
                break

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
