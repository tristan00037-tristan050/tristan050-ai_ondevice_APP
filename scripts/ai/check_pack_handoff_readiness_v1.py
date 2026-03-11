#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

try:
    from .common_pack_build_v1 import read_json, require_file, safe_print_kv
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common_pack_build_v1 import read_json, require_file, safe_print_kv


REQUIRED_ARTIFACTS = [
    "model.onnx",
    "tokenizer.json",
    "config.json",
    "chat_template.jinja",
    "runtime_manifest.json",
    "SHA256SUMS",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir", default="packs/micro_default")
    parser.add_argument("--eval-summary", default=None)
    parser.add_argument("--variance-summary", default=None)
    args = parser.parse_args()

    pack_dir = Path(args.pack_dir)

    missing = []
    for name in REQUIRED_ARTIFACTS:
        path = pack_dir / name
        if not path.exists():
            missing.append(name)

    if missing:
        raise SystemExit(f"PACK_HANDOFF_NOT_READY:MISSING={','.join(missing)}")

    manifest = read_json(pack_dir / "runtime_manifest.json")
    if manifest.get("status") != "verified":
        safe_print_kv("PACK_HANDOFF_STATUS_WARNING", manifest.get("status", "UNKNOWN"))

    if args.eval_summary:
        eval_path = Path(args.eval_summary)
        if not eval_path.exists():
            raise SystemExit(f"PACK_HANDOFF_NOT_READY:EVAL_SUMMARY_MISSING={eval_path}")
        eval_data = read_json(eval_path)
        schema_pass_rate = eval_data.get("schema_pass_rate", 0)
        slo = eval_data.get("slo_schema_pass_rate", 0.98)
        safe_print_kv("EVAL_SCHEMA_PASS_RATE", str(schema_pass_rate))
        if schema_pass_rate < slo:
            raise SystemExit(
                f"PACK_HANDOFF_NOT_READY:EVAL_SCHEMA_PASS_RATE={schema_pass_rate}<{slo}"
            )
        safe_print_kv("EVAL_SCHEMA_PASS_RATE_OK", "1")

    if args.variance_summary:
        var_path = Path(args.variance_summary)
        if not var_path.exists():
            raise SystemExit(f"PACK_HANDOFF_NOT_READY:VARIANCE_SUMMARY_MISSING={var_path}")
        var_data = read_json(var_path)
        safe_print_kv("VARIANCE_SAMPLE_COUNT", str(var_data.get("sample_count", 0)))
        safe_print_kv("VARIANCE_DECODE_TPS_MEAN", str(var_data.get("decode_tps_mean", 0)))
        safe_print_kv("VARIANCE_LATENCY_P95_MS", str(var_data.get("latency_p95_ms", 0)))
        safe_print_kv("VARIANCE_SUMMARY_OK", "1")

    safe_print_kv("PACK_HANDOFF_READINESS_OK", "1")


if __name__ == "__main__":
    main()
