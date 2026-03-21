#!/usr/bin/env python3
"""
eval_butler_v1.py — 버틀러 6개 기능 schema 검증 eval (Phase C, v52)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase_c_shared import (
    DEFAULT_LATENCY_BUDGET_MS,
    add_common_cli,
    check_latency_budget,
    dry_run_payload,
    infer,
    load_model,
    load_tool_schema,
    validate_output_schema,
    verify_phase_c_eval_records,
)


def load_records(eval_file: str) -> list[dict]:
    rows = []
    with open(eval_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_eval(args: argparse.Namespace) -> dict:
    schema = load_tool_schema(args.schema_file)
    records = load_records(args.eval_file)
    dataset_ok, dataset_errors = verify_phase_c_eval_records(records, schema)
    if not dataset_ok:
        raise RuntimeError("PHASE_C_EVAL_DATASET_INVALID: " + "; ".join(dataset_errors[:5]))
    tokenizer, model, meta = load_model(
        adapter_dir=args.adapter_dir,
        schema_file=args.schema_file,
        base_model_id=args.base_model_id,
        device_preference=args.device_preference,
        load_mode=args.load_mode,
        trust_remote_code=args.trust_remote_code,
    )
    print(f"  eval 데이터: {len(records)}건")
    total = len(records)
    passed = 0
    results = []
    latencies = []
    for i, rec in enumerate(records, 1):
        prompt = rec.get("prompt", "")
        function = rec.get("function", "dialogue")
        output, latency_ms = infer(tokenizer, model, prompt, max_new_tokens=args.max_new_tokens)
        latencies.append(latency_ms)
        schema_ok, reason = validate_output_schema(
            output,
            function,
            schema=schema,
            min_len=rec.get("min_len", 20),
            expected_tool_name=rec.get("expected_tool_name"),
            expected_arguments=rec.get("expected_arguments"),
        )
        if schema_ok:
            passed += 1
        print(f"  [{i:3d}/{total}] {'PASS' if schema_ok else 'FAIL'} function={function} len={len(output)} reason={reason}")
        results.append({
            "index": i,
            "function": function,
            "schema_ok": schema_ok,
            "reason": reason,
            "output_len": len(output),
            "latency_ms": round(latency_ms, 2),
        })
    schema_pass_rate = round((passed / total) if total else 0.0, 4)
    latency_stats = check_latency_budget(latencies, args.latency_budget_ms)
    eval_ok = int(schema_pass_rate == 1.0 and latency_stats["latency_budget_ok"])
    return {
        "EVAL_BUTLER_OK": eval_ok,
        "PHASE_C_EVAL_DATASET_OK": 1,
        "total": total,
        "passed": passed,
        "schema_pass_rate": schema_pass_rate,
        **latency_stats,
        "adapter_dir": args.adapter_dir,
        **meta,
        "eval_file": args.eval_file,
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="butler_model_v1 eval")
    add_common_cli(ap)
    ap.add_argument("--eval-file", default="data/phase_c/butler_eval_v1.jsonl")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--latency-budget-ms", type=float, default=DEFAULT_LATENCY_BUDGET_MS)
    ap.add_argument("--out", default="tmp/eval_result.json")
    args = ap.parse_args()

    print("=== butler_model_v1 Eval ===")
    records = load_records(args.eval_file)
    schema = load_tool_schema(args.schema_file)
    dataset_ok, dataset_errors = verify_phase_c_eval_records(records, schema)
    if args.dry_run:
        result = dry_run_payload(
            "eval", args,
            extra={
                "eval_file": args.eval_file,
                "eval_records": len(records),
                "PHASE_C_EVAL_DATASET_OK": 1 if dataset_ok else 0,
                "dataset_errors": dataset_errors[:10],
                "latency_budget_ms": args.latency_budget_ms,
                "why_not_ok_in_dry_run": "dry-run은 실제 추론을 수행하지 않으므로 EVAL_BUTLER_OK는 0으로 유지됩니다.",
            },
        )
    else:
        result = run_eval(args)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {args.out}")
    if args.dry_run:
        print(f"EVAL_READY={result.get('EVAL_READY', 0)}")
        print(f"PHASE_C_EVAL_DATASET_OK={result.get('PHASE_C_EVAL_DATASET_OK', 0)}")
    else:
        print(f"EVAL_BUTLER_OK={result.get('EVAL_BUTLER_OK', 0)}")
        print(f"schema_pass_rate={result['schema_pass_rate']}")
        print(f"p95_latency_ms={result.get('p95_latency_ms', 0.0)}")
    if not args.dry_run and result.get("EVAL_BUTLER_OK") != 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
