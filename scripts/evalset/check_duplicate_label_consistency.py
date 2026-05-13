#!/usr/bin/env python3
"""check_duplicate_label_consistency.py — 단계 6.5.5+ Day 6 CI Gate G22.

알고리즘 팀 확정 명세 (2026-05-14):
  Scope:       모든 row
  Group key:   raw_digest16
  Hard fields: intent_type / deadline_type / auto_apply_allowed
  Priority:    gold_v1 > gold_reviewed > adjudicated > double_labeled > draft
  Exception:   허용 없음 (context_digest16 도입 후만 검토 — Day 7+)

fail_class (심각도 순):
  GOLD_V1_DUPLICATE_CONFLICT    — gold_v1 두 개 이상 + 라벨 불일치
  REVIEWED_DUPLICATE_CONFLICT   — gold_reviewed 두 개 이상 + 라벨 불일치
  DUPLICATE_LABEL_INCONSISTENCY — 일반 불일치
  JSON_PARSE_ERROR

각 violation 그룹마다 recommended_truth_source 출력 (priority 최상위 sample_id).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

HARD_FIELDS = ["intent_type", "deadline_type", "auto_apply_allowed"]

LABEL_STATUS_PRIORITY = {
    "gold_v1":        5,
    "gold_reviewed":  4,
    "adjudicated":    3,
    "double_labeled": 2,
    "draft":          1,
}

SEVERITY = {
    "GOLD_V1_DUPLICATE_CONFLICT":    3,
    "REVIEWED_DUPLICATE_CONFLICT":   2,
    "DUPLICATE_LABEL_INCONSISTENCY": 1,
}


def _get_priority(status: Optional[str]) -> int:
    return LABEL_STATUS_PRIORITY.get(status or "", 0)


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

    items_by_digest: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    parse_errors: List[Dict[str, Any]] = []
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
                parse_errors.append({"line_no": line_no, "error": str(e)})
                continue
            digest = item.get("raw_digest16")
            if digest:
                item["_line_no"] = line_no
                items_by_digest[digest].append(item)

    if parse_errors:
        report = {
            "ok":                False,
            "fail_class":        "JSON_PARSE_ERROR",
            "total_items":       total,
            "violation_count":   len(parse_errors),
            "parse_errors":      parse_errors[:50],
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    duplicate_groups: List[Dict[str, Any]] = []
    duplicate_count = 0

    for digest, items in items_by_digest.items():
        if len(items) < 2:
            continue
        duplicate_count += 1

        # 충돌 필드 식별
        conflicts: List[str] = []
        values_map: Dict[str, List[str]] = {}
        for field in HARD_FIELDS:
            vals = sorted({str(it.get(field)) for it in items})
            if len(vals) > 1:
                conflicts.append(field)
                values_map[field] = vals
        if not conflicts:
            continue

        # fail_class 결정
        statuses = [it.get("label_status") for it in items]
        gold_v1_count    = sum(1 for s in statuses if s == "gold_v1")
        reviewed_count   = sum(1 for s in statuses if s == "gold_reviewed")
        if gold_v1_count >= 2:
            fail_class = "GOLD_V1_DUPLICATE_CONFLICT"
        elif reviewed_count >= 2:
            fail_class = "REVIEWED_DUPLICATE_CONFLICT"
        else:
            fail_class = "DUPLICATE_LABEL_INCONSISTENCY"

        # 권장 정정 라벨 (priority 최상위)
        sorted_items = sorted(
            items, key=lambda x: _get_priority(x.get("label_status")), reverse=True,
        )
        recommended_source = sorted_items[0].get("sample_id")

        duplicate_groups.append({
            "raw_digest16":             digest,
            "sample_ids":               [it.get("sample_id") for it in items],
            "label_statuses":           statuses,
            "conflicts":                conflicts,
            "values":                   values_map,
            "fail_class":               fail_class,
            "recommended_truth_source": recommended_source,
            "line_nos":                 [it.get("_line_no") for it in items],
        })

    if duplicate_groups:
        # 심각도 최상위 fail_class 노출
        primary = max(
            (g["fail_class"] for g in duplicate_groups),
            key=lambda c: SEVERITY.get(c, 0),
        )
        report = {
            "ok":                       False,
            "fail_class":               primary,
            "total_items":              total,
            "duplicate_groups_checked": duplicate_count,
            "violation_count":          len(duplicate_groups),
            "duplicate_groups":         duplicate_groups[:50],
        }
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1

    report = {
        "ok":                       True,
        "fail_class":               None,
        "total_items":              total,
        "unique_digests":           len(items_by_digest),
        "duplicate_groups_checked": duplicate_count,
        "violation_count":          0,
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
