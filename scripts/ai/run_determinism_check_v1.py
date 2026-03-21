#!/usr/bin/env python3
"""
run_determinism_check_v1.py — 동일 입력 3회 추론 일치성 검증 (Phase C, v52)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase_c_shared import DEFAULT_LATENCY_BUDGET_MS, SMOKE_CASES, add_common_cli, check_latency_budget, dry_run_payload, infer, load_model, sha256_text


def run_determinism(args: argparse.Namespace) -> dict:
    tokenizer, model, meta = load_model(
        adapter_dir=args.adapter_dir,
        schema_file=args.schema_file,
        base_model_id=args.base_model_id,
        device_preference=args.device_preference,
        load_mode=args.load_mode,
        trust_remote_code=args.trust_remote_code,
    )
    prompt = args.prompt or SMOKE_CASES[0]["prompt"]
    outputs = []
    digests = []
    latencies = []
    for idx in range(args.repeat):
        text, latency_ms = infer(tokenizer, model, prompt, max_new_tokens=args.max_new_tokens)
        outputs.append(text)
        digests.append(sha256_text(text))
        latencies.append(latency_ms)
        print(f"Run {idx + 1}: len={len(text)} latency={latency_ms:.1f}ms digest={digests[-1][:16]}")
    deterministic = len(set(outputs)) == 1
    latency_stats = check_latency_budget(latencies, args.latency_budget_ms)
    ok = int(deterministic and latency_stats["latency_budget_ok"])
    return {
        "DETERMINISM_OK": ok,
        "repeat": args.repeat,
        "prompt_digest": sha256_text(prompt),
        "output_digests": digests,
        "latency_ms": [round(x, 2) for x in latencies],
        **latency_stats,
        **meta,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="butler_model_v1 determinism check")
    add_common_cli(ap)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--prompt")
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--latency-budget-ms", type=float, default=DEFAULT_LATENCY_BUDGET_MS)
    ap.add_argument("--out", default="tmp/determinism_result.json")
    args = ap.parse_args()

    print("=== butler_model_v1 Determinism Check ===")
    if args.dry_run:
        result = dry_run_payload(
            "determinism", args,
            extra={
                "repeat": args.repeat,
                "latency_budget_ms": args.latency_budget_ms,
                "why_not_ok_in_dry_run": "dry-run은 실제 추론을 수행하지 않으므로 DETERMINISM_OK는 계산되지 않습니다.",
            },
        )
    else:
        result = run_determinism(args)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {args.out}")
    if args.dry_run:
        print(f"DETERMINISM_READY={result.get('DETERMINISM_READY', 0)}")
    else:
        print(f"DETERMINISM_OK={result.get('DETERMINISM_OK', 0)}")
    if not args.dry_run and result.get("DETERMINISM_OK") != 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
