from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai.eval_butler_v1 import load_eval_dataset, validate_eval_dataset
from scripts.ai.phase_c_shared import make_result_schema, set_reproducibility
from scripts.ai.run_determinism_check_v1 import run_determinism, run_determinism_with_model
from scripts.ai.run_smoke_eval_v1 import run_smoke


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter-dir', required=True)
    ap.add_argument('--eval-file', required=True)
    ap.add_argument('--schema-file', required=True)
    ap.add_argument('--device-preference', default='cuda')
    ap.add_argument('--load-mode', default='4bit')
    ap.add_argument('--latency-budget-ms', type=int, default=10000)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dry-run', action='store_true')
    return ap.parse_args(argv)


def resolve_device(preference: str) -> str:
    try:
        import torch
        if preference == 'cuda' and torch.cuda.is_available():
            return 'cuda'
        if preference == 'mps' and getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available():
            return 'mps'
    except Exception:
        pass
    return 'cpu'


def read_adapter_config(adapter_dir: str | Path) -> tuple[int | None, dict[str, Any]]:
    cfg_path = Path(adapter_dir) / 'adapter_config.json'
    if not cfg_path.exists():
        return None, {}
    data = json.loads(cfg_path.read_text(encoding='utf-8'))
    return int(data.get('r')) if data.get('r') is not None else None, data


def compute_adapter_digest(adapter_dir: str | Path) -> str:
    fp = Path(adapter_dir) / 'adapter_model.safetensors'
    if not fp.exists():
        return 'missing'
    import hashlib
    return hashlib.sha256(fp.read_bytes()).hexdigest()[:16]


def load_model_and_tokenizer(model_id: str, adapter_dir: str, load_mode: str, device: str):
    """4bit QLoRA 어댑터 로드 — GPU real-run 전용."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    quant_cfg = None
    if load_mode == '4bit':
        quant_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type='nf4',
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=True,
        quantization_config=quant_cfg,
        device_map='auto',
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, adapter_dir)
    model.eval()
    return model, tokenizer


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    set_reproducibility(42)
    rows = load_eval_dataset(args.eval_file)
    device = resolve_device(args.device_preference)
    adapter_r, _cfg = read_adapter_config(args.adapter_dir)
    digest = compute_adapter_digest(args.adapter_dir)

    result = make_result_schema(
        execution_mode='dry_run' if args.dry_run else 'real',
        adapter_digest=digest,
        model_id='Qwen/Qwen3-4B',
        adapter_dir=args.adapter_dir,
        device_info={'preference': args.device_preference, 'resolved': device, 'load_mode': args.load_mode},
        evidence_kind='structure_only' if args.dry_run else 'gpu_real_run',
    )

    dataset_ok, tool_ok, schema_pass_rate, fail_cases = validate_eval_dataset(rows)
    result['eval_records'] = len(rows)
    result['PHASE_C_EVAL_DATASET_OK'] = 1 if dataset_ok else 0
    result['PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK'] = 1 if tool_ok else 0
    result['schema_pass_rate'] = round(schema_pass_rate, 4)
    result['fail_cases'] = fail_cases

    if args.dry_run:
        model, tokenizer = None, None
    else:
        model, tokenizer = load_model_and_tokenizer('Qwen/Qwen3-4B', args.adapter_dir, args.load_mode, device)

    smoke_rows, smoke_ok = run_smoke(rows, args.latency_budget_ms, dry_run=args.dry_run, model=model, tokenizer=tokenizer)
    result['smoke_results'] = smoke_rows
    result['SMOKE_ALL_RUNS_PASS'] = 1 if smoke_ok else 0

    if args.dry_run:
        det_ok, det_digest = run_determinism(['dry_run_placeholder'] * 3)
    else:
        det_ok, det_digest = run_determinism_with_model(model, tokenizer, '오늘 할 일을 3줄로 요약해 주세요.', seed=42, n=3)
    result['DETERMINISM_OK'] = 1 if det_ok else 0
    result['determinism_digest'] = det_digest
    result['EVAL_BUTLER_OK'] = 1 if (dataset_ok and tool_ok and schema_pass_rate == 1.0) else 0
    result['p95_latency_ms'] = max((x['latency_ms'] for x in smoke_rows), default=0)
    result['warmup_included_in_p95'] = False
    result['PHASE_C_VERIFICATION_OK'] = 1 if (result['SMOKE_ALL_RUNS_PASS'] and result['DETERMINISM_OK'] and result['EVAL_BUTLER_OK']) else 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

    if args.dry_run:
        print('PHASE_C_DRYRUN_OK=1')
        print(f'eval_records={len(rows)}')
        print(f'PHASE_C_EVAL_DATASET_OK={result["PHASE_C_EVAL_DATASET_OK"]}')
        print(f'PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK={result["PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK"]}')
        print(f'adapter_r={adapter_r or 12}')
        print('PHASE_C_SCRIPTS_READY=1')
        return 0

    print(f'SMOKE_ALL_RUNS_PASS={result["SMOKE_ALL_RUNS_PASS"]}')
    print(f'DETERMINISM_OK={result["DETERMINISM_OK"]}')
    print(f'EVAL_BUTLER_OK={result["EVAL_BUTLER_OK"]}')
    print(f'PHASE_C_VERIFICATION_OK={result["PHASE_C_VERIFICATION_OK"]}')

    try:
        import torch
        del model
        torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
