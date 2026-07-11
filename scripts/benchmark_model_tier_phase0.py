#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.model_tier.benchmark_contracts import (
    BenchmarkSample,
    summarize_benchmark,
)


SAMPLE_FIELDS = frozenset(field.name for field in fields(BenchmarkSample))


def _load_samples(path: Path) -> list[BenchmarkSample]:
    samples: list[BenchmarkSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            payload: Any = json.loads(line)
            if not isinstance(payload, dict) or set(payload) != SAMPLE_FIELDS:
                raise ValueError(f"BENCHMARK_SAMPLE_EXACT_KEYS_REQUIRED:{line_number}")
            sample = BenchmarkSample(**payload)
            sample.validate()
            samples.append(sample)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate digest-only Butler Phase 0 benchmark samples."
    )
    parser.add_argument("samples_jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = summarize_benchmark(_load_samples(args.samples_jsonl))
    except Exception as exc:
        print("MODEL_TIER_BENCHMARK_OK=0")
        print(f"ERROR_CODE={str(exc).split(':', 1)[0] or 'BENCHMARK_FAILED'}")
        return 1
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    print("MODEL_TIER_BENCHMARK_OK=1", file=sys.stderr)
    print(
        f"MODEL_TIER_BENCHMARK_PROTOCOL_COMPLETE={1 if result['protocol_complete'] else 0}",
        file=sys.stderr,
    )
    return 0 if result["protocol_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
