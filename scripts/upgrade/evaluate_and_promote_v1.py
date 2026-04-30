#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(description='Promotion gate for continual learning cycle')
    ap.add_argument('--sanity-json', required=True)
    ap.add_argument('--toolcall-json', default=None)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-global-dup-rate', type=float, default=0.02)
    args = ap.parse_args()

    sanity = json.loads(Path(args.sanity_json).read_text(encoding='utf-8'))
    toolcall = json.loads(Path(args.toolcall_json).read_text(encoding='utf-8')) if args.toolcall_json else {}
    global_dup = float(sanity.get('GLOBAL_DUPLICATE_PROMPT_RATE', 1.0))
    tool_pass = float(toolcall.get('schema_pass_rate', 1.0)) if toolcall else 1.0

    passed = (
        sanity.get('TRAIN_EVAL_INPUT_SANITY_V1_OK', 0) == 1 and
        sanity.get('DATASET_SPLIT_NO_LEAKAGE_OK', 0) == 1 and
        global_dup <= args.max_global_dup_rate and
        tool_pass >= 1.0
    )
    result = {
        'AUTO_PROMOTE_GATE_OK': int(passed),
        'GLOBAL_DUPLICATE_PROMPT_RATE': global_dup,
        'tool_call_schema_pass_rate': tool_pass,
        'decision': 'promote' if passed else 'hold',
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"AUTO_PROMOTE_GATE_OK={result['AUTO_PROMOTE_GATE_OK']}")

if __name__ == '__main__':
    main()
