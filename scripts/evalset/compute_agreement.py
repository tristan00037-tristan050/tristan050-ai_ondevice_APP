#!/usr/bin/env python3
"""compute_agreement.py — 단계 6.5.5 CI Gate #5.

2인 라벨링 합의도 (intent_type / deadline_type / auto_apply_allowed).

Day 1: 같은 sample_id 의 2 라인 비교 (legacy).
Day 3 강화: 단일 sample 안의 annotator_a / annotator_b 필드 직접 비교.
            Cohen's kappa 자체 구현 (sklearn 의존성 회피).

fail-closed (Day 1 P1 정정 유지):
- 비교 가능한 쌍 0개 → NO_COMPARABLE_PAIRS
- 임계값 미달 → BELOW_AGREEMENT_THRESHOLD
- JSON parse → JSON_PARSE_ERROR

기준 (CARD1_EVALSET_SPEC §6):
- intent_type        ≥ 0.85
- deadline_type      ≥ 0.80
- auto_apply_allowed ≥ 0.95
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

THRESHOLDS = {
    "intent_type":        0.85,
    "deadline_type":      0.80,
    "auto_apply_allowed": 0.95,
}
FIELDS = list(THRESHOLDS.keys())


def cohen_kappa(a_labels: List[Any], b_labels: List[Any]) -> float:
    """Cohen's kappa 자체 구현 (range [-1, 1]). 빈 입력 → 0.0."""
    if not a_labels or len(a_labels) != len(b_labels):
        return 0.0
    n = len(a_labels)
    classes = sorted(set(a_labels) | set(b_labels), key=lambda x: str(x))
    if len(classes) < 2:
        return 1.0 if all(a == b for a, b in zip(a_labels, b_labels)) else 0.0
    p_o = sum(1 for a, b in zip(a_labels, b_labels) if a == b) / n
    a_count = Counter(a_labels)
    b_count = Counter(b_labels)
    p_e = sum((a_count.get(c, 0) / n) * (b_count.get(c, 0) / n) for c in classes)
    if p_e >= 1.0:
        return 1.0
    return round((p_o - p_e) / (1 - p_e), 4)


def _collect_pairs_from_annotators(items: List[dict], field: str) \
        -> Tuple[List[Any], List[Any]]:
    a_list, b_list = [], []
    for it in items:
        a = it.get("annotator_a")
        b = it.get("annotator_b")
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if field in a and field in b:
            a_list.append(a[field])
            b_list.append(b[field])
    return a_list, b_list


def _collect_pairs_legacy(items: List[dict], field: str) \
        -> Tuple[List[Any], List[Any]]:
    by_sid: Dict[str, List[Any]] = defaultdict(list)
    for it in items:
        sid = it.get("sample_id")
        if sid is None or field not in it:
            continue
        by_sid[sid].append(it[field])
    a_list, b_list = [], []
    for vals in by_sid.values():
        if len(vals) >= 2:
            a_list.append(vals[0])
            b_list.append(vals[1])
    return a_list, b_list


def simple_agreement(items: List[dict], field: str) -> dict:
    a_list, b_list = _collect_pairs_from_annotators(items, field)
    used = "annotator_fields"
    if not a_list:
        a_list, b_list = _collect_pairs_legacy(items, field)
        used = "legacy_sample_id"

    total = len(a_list)
    if total == 0:
        return {
            "ok":            False,
            "rate":          None,
            "kappa":         None,
            "total_pairs":   0,
            "agreed_pairs":  0,
            "source":        used,
            "fail_class":    "NO_COMPARABLE_PAIRS",
            "message":       f"{field}: 비교 가능한 2인 라벨 쌍이 없음",
        }
    agreed = sum(1 for a, b in zip(a_list, b_list) if a == b)
    rate   = round(agreed / total, 4)
    kappa  = cohen_kappa(a_list, b_list)
    return {
        "ok":           True,
        "rate":         rate,
        "kappa":        kappa,
        "total_pairs":  total,
        "agreed_pairs": agreed,
        "source":       used,
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

    report = {"ok": overall_ok, "fields": field_results}
    if not overall_ok:
        for r in field_results.values():
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
