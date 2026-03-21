#!/usr/bin/env python3
"""
run_smoke_eval_v1.py — butler_model_v1 실제 추론 smoke test (Phase C, v52)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from phase_c_shared import (
    SMOKE_CASES,
    DEFAULT_LATENCY_BUDGET_MS,
    add_common_cli,
    check_latency_budget,
    dry_run_payload,
    infer,
    load_model,
    load_tool_schema,
    sha256_text,
    validate_output_schema,
)


def run_smoke(args: argparse.Namespace) -> dict:
    schema = load_tool_schema(args.schema_file)
    tokenizer, model, meta = load_model(
        adapter_dir=args.adapter_dir,
        schema_file=args.schema_file,
        base_model_id=args.base_model_id,
        device_preference=args.device_preference,
        load_mode=args.load_mode,
        trust_remote_code=args.trust_remote_code,
    )
    all_pass = True
    runs = []
    case_digest_history: dict[str, list[str]] = defaultdict(list)
    all_latencies: list[float] = []

    for run_idx in range(args.repeat):
        run_pass = True
        cases = []
        print(f"\n  ── Smoke Run {run_idx + 1}/{args.repeat} ──")
        for case in SMOKE_CASES:
            output, latency_ms = infer(tokenizer, model, case["prompt"], max_new_tokens=args.max_new_tokens)
            output_digest = sha256_text(output)
            prompt_digest = sha256_text(case["prompt"])
            case_key = f"{case['function']}::{prompt_digest}"
            case_digest_history[case_key].append(output_digest)
            all_latencies.append(latency_ms)
            empty_fail = len(output.strip()) == 0
            echo_fail = output_digest == prompt_digest
            schema_ok, schema_reason = validate_output_schema(
                output,
                case["function"],
                schema=schema,
                min_len=case["min_len"],
                expected_tool_name=case.get("expected_tool_name"),
                expected_arguments=case.get("expected_arguments"),
            )
            case_pass = (not empty_fail) and (not echo_fail) and schema_ok
            if not case_pass:
                run_pass = False
            print(
                f"    [{'PASS' if case_pass else 'FAIL'}] function={case['function']} "
                f"len={len(output)} latency={latency_ms:.1f}ms reason={'ok' if case_pass else schema_reason}"
            )
            cases.append({
                "function": case["function"],
                "prompt_digest": prompt_digest[:16],
                "output_digest": output_digest[:16],
                "output_len": len(output),
                "latency_ms": round(latency_ms, 2),
                "empty_fail": empty_fail,
                "echo_fail": echo_fail,
                "schema_ok": schema_ok,
                "schema_reason": schema_reason,
                "pass": case_pass,
            })
        runs.append({"run": run_idx + 1, "pass": run_pass, "cases": cases})
        all_pass = all_pass and run_pass

    determinism_failures = []
    for case_key, digests in case_digest_history.items():
        if len(set(digests)) != 1:
            determinism_failures.append({"case": case_key, "digests": digests})
    determinism_ok = len(determinism_failures) == 0
    latency_stats = check_latency_budget(all_latencies, args.latency_budget_ms)
    final_ok = all_pass and determinism_ok and latency_stats["latency_budget_ok"]
    return {
        "SMOKE_ALL_RUNS_PASS": 1 if final_ok else 0,
        "repeat": args.repeat,
        "all_pass": all_pass,
        "DETERMINISM_OK": 1 if determinism_ok else 0,
        "determinism_failures": determinism_failures,
        **latency_stats,
        "adapter_dir": args.adapter_dir,
        **meta,
        "runs": runs,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="butler_model_v1 smoke test")
    add_common_cli(ap)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--latency-budget-ms", type=float, default=DEFAULT_LATENCY_BUDGET_MS)
    ap.add_argument("--out", default="tmp/smoke_result.json")
    args = ap.parse_args()

    print("=== butler_model_v1 Smoke Test ===")
    if args.dry_run:
        result = dry_run_payload(
            "smoke", args,
            extra={
                "repeat": args.repeat,
                "max_new_tokens": args.max_new_tokens,
                "latency_budget_ms": args.latency_budget_ms,
                "why_not_ok_in_dry_run": "dry-run은 실제 모델 로드/추론을 수행하지 않으므로 SMOKE_ALL_RUNS_PASS는 계산되지 않습니다.",
            },
        )
    else:
        result = run_smoke(args)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {args.out}")
    if args.dry_run:
        print(f"SMOKE_READY={result.get('SMOKE_READY', 0)}")
    else:
        print(f"SMOKE_ALL_RUNS_PASS={result.get('SMOKE_ALL_RUNS_PASS', 0)}")
        print(f"DETERMINISM_OK={result.get('DETERMINISM_OK', 0)}")
        print(f"p95_latency_ms={result.get('p95_latency_ms', 0.0)}")
    if not args.dry_run and not result.get("SMOKE_ALL_RUNS_PASS", 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
