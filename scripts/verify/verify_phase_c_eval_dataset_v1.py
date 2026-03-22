#!/usr/bin/env python3
"""
verify_phase_c_eval_dataset_v1.py — Phase C eval dataset 정합성 검사
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'scripts' / 'ai') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts' / 'ai'))

from phase_c_shared import load_tool_schema, verify_phase_c_eval_records


def load_records(path: str) -> list[dict]:
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description='Phase C eval dataset verifier')
    ap.add_argument('--schema', default='schemas/tool_call_schema_v3.json')
    ap.add_argument('--eval-file', default='data/phase_c/butler_eval_v1.jsonl')
    args = ap.parse_args()
    schema = load_tool_schema(args.schema)
    records = load_records(args.eval_file)
    ok, errors = verify_phase_c_eval_records(records, schema)
    print(f'eval_records={len(records)}')
    if not ok:
        for e in errors[:20]:
            print(e, file=sys.stderr)
        print('PHASE_C_EVAL_DATASET_OK=0')
        sys.exit(1)
    print('PHASE_C_EVAL_DATASET_OK=1')
    print('PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK=1')
    sys.exit(0)


if __name__ == '__main__':
    main()
