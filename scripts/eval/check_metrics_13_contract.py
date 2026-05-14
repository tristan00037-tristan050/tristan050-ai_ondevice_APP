#!/usr/bin/env python3
"""check_metrics_13_contract.py — Codex P1 정정 후 metrics_13 contract 검증.

검사:
  1. dataset_id == card1_evalset_v1_1_500
  2. dataset_file == tests/fixtures/card1_evalset_v1_1_500.jsonl
  3. 'auto_apply_accuracy' 키 (단독 필드) 미사용
  4. verdict == MEASURED_ONLY
  5. 13지표 모든 키 존재 (Tier 1~4)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_FLAT_KEYS = [
    # Tier 1 hard safety
    "verifier_error_auto_apply_count",
    "false_deadline_rate",
    "no_action_fp_rate",
    "g22_strict_warning_count",
    "g23_hard_violation_count",
    # Tier 2 auto apply
    "auto_apply_precision",
    "auto_apply_recall",
    # Tier 3 extraction quality
    "normalized_action_f1",
    "multi_action_split_accuracy",
    "deadline_f1",
    "schema_valid_rate",
    # Tier 4 calibration
    "action_ece_after",
    "intent_ece_after",
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(json.dumps({"ok": False, "fail_class": "METRICS_13_MISSING",
                          "path": str(in_path)}, ensure_ascii=False))
        return 1
    obj = json.loads(in_path.read_text(encoding="utf-8"))
    bad = []

    if obj.get("dataset_id") != "card1_evalset_v1_1_500":
        bad.append(f"dataset_id_invalid:{obj.get('dataset_id')}")
    if obj.get("dataset_file") != "tests/fixtures/card1_evalset_v1_1_500.jsonl":
        bad.append(f"dataset_file_invalid:{obj.get('dataset_file')}")
    if "auto_apply_accuracy" in json.dumps(obj, ensure_ascii=False):
        bad.append("auto_apply_accuracy_forbidden")
    if obj.get("verdict") != "MEASURED_ONLY":
        bad.append(f"verdict_must_be_MEASURED_ONLY:{obj.get('verdict')}")
    for k in REQUIRED_FLAT_KEYS:
        if k not in obj:
            bad.append(f"missing:{k}")

    if bad:
        print(json.dumps({"ok": False,
                          "fail_class": "METRICS_13_CONTRACT_FAIL",
                          "bad": bad}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True,
                      "fail_class": None,
                      "message": "metrics_13 contract pass"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
