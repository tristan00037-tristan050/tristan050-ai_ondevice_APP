#!/usr/bin/env python3
"""
verify_ai15_dryrun_result_consistency_v1.py
- qlora_dryrun_result.json과 effective_sft_kwargs / eval 전략 일관성 검증
- 출력: stdout에 key=value 및 ERROR_CODE=만 (레포 verify 계약 정렬)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="AI-15 dryrun result consistency verifier")
    ap.add_argument(
        "--dryrun-json",
        default="tmp/qlora_dryrun_result.json",
        help="dry-run 결과 JSON 경로",
    )
    args = ap.parse_args()

    p = Path(args.dryrun_json)
    if not p.exists():
        print("AI15_DRYRUN_RESULT_PRESENT_OK=0")
        print("ERROR_CODE=AI15_DRYRUN_JSON_MISSING", file=sys.stderr)
        return 1

    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("AI15_DRYRUN_RESULT_PRESENT_OK=0")
        print("ERROR_CODE=AI15_DRYRUN_JSON_PARSE", file=sys.stderr)
        return 1

    print("AI15_DRYRUN_RESULT_PRESENT_OK=1")

    error_codes: list[str] = []
    eval_present = bool(obj.get("eval_file"))

    expected_lbme = eval_present
    actual_lbme = bool(obj.get("load_best_model_at_end"))
    if expected_lbme != actual_lbme:
        error_codes.append("LOAD_BEST_MODEL_AT_END_MISMATCH")

    expected_eval_strategy = "steps" if eval_present else "no"
    actual_eval_strategy = obj.get("eval_strategy", "")
    if expected_eval_strategy != actual_eval_strategy:
        error_codes.append("EVAL_STRATEGY_MISMATCH")

    if eval_present and not obj.get("metric_for_best_model"):
        error_codes.append("METRIC_FOR_BEST_MODEL_MISSING")

    eff = obj.get("effective_sft_kwargs")
    if not isinstance(eff, dict):
        error_codes.append("EFFECTIVE_SFT_KWARGS_INVALID")
    else:
        for key in ("load_best_model_at_end", "eval_strategy"):
            top_val = obj.get(key)
            eff_val = eff.get(key)
            if top_val != eff_val:
                error_codes.append(f"TOP_EFF_MISMATCH:{key}")

    ok = len(error_codes) == 0
    print(f"AI15_DRYRUN_RESULT_MATCHES_EFFECTIVE_CONFIG_OK={1 if ok else 0}")
    if not ok:
        print("ERROR_CODE=" + "|".join(error_codes), file=sys.stderr)
        return 1

    print("AI15_EFFECTIVE_STRATEGIES_SERIALIZED_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
