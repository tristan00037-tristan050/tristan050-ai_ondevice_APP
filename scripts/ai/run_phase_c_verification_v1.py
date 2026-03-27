#!/usr/bin/env python3
"""Reference Phase C verifier for AI-20.

This helper is included so the delivery bundle is runnable end-to-end even when the
original repository helper is absent. It is intentionally conservative:
- it requires real adapter artifacts for a pass,
- it enforces enable_thinking=False,
- it writes a JSON result compatible with downstream verifiers.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from scripts.ai.phase_c_shared import dump_json, load_jsonl, make_phase_c_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter-dir', required=True)
    parser.add_argument('--eval-file', required=True)
    parser.add_argument('--schema-file', required=True)
    parser.add_argument('--device-preference', default='cuda')
    parser.add_argument('--load-mode', default='4bit')
    parser.add_argument('--latency-budget-ms', type=int, default=8000)
    parser.add_argument('--out', required=True)
    parser.add_argument('--max-samples', type=int, default=8)
    return parser.parse_args()


def resolve_base_model_id(adapter_dir: Path) -> str:
    adapter_config = adapter_dir / 'adapter_config.json'
    if adapter_config.exists():
        payload = json.loads(adapter_config.read_text(encoding='utf-8'))
        return payload.get('base_model_name_or_path', 'Qwen/Qwen3-4B')
    metadata = adapter_dir / 'ai20_training_metadata.json'
    if metadata.exists():
        payload = json.loads(metadata.read_text(encoding='utf-8'))
        return payload.get('base_model_id', 'Qwen/Qwen3-4B')
    return 'Qwen/Qwen3-4B'


def load_model_stack(adapter_dir: Path, load_mode: str, device_preference: str) -> tuple[Any, Any]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    base_model_id = resolve_base_model_id(adapter_dir)
    tokenizer = AutoTokenizer.from_pretrained(base_model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model_kwargs: dict[str, Any] = {
        'enable_thinking': False,
        'device_map': 'auto' if device_preference == 'cuda' else None,
    }
    if load_mode == '4bit':
        model_kwargs['torch_dtype'] = torch.bfloat16
        model_kwargs['quantization_config'] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    base_model = AutoModelForCausalLM.from_pretrained(base_model_id, **model_kwargs)
    model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    return tokenizer, model


def build_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    if isinstance(record.get('messages'), list):
        return record['messages']
    prompt = record.get('prompt') or record.get('instruction') or record.get('input') or ''
    system = record.get('system')
    messages: list[dict[str, str]] = []
    if system:
        messages.append({'role': 'system', 'content': str(system)})
    messages.append({'role': 'user', 'content': str(prompt)})
    return messages


def generate_one(tokenizer: Any, model: Any, record: dict[str, Any]) -> tuple[str, float]:
    import torch

    messages = build_messages(record)
    try:
        rendered = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_tensors='pt',
        )
    except TypeError:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        rendered = tokenizer(text, return_tensors='pt', add_special_tokens=False)
        rendered = rendered['input_ids']

    if hasattr(rendered, 'to'):
        rendered = rendered.to(model.device)
        inputs = {'input_ids': rendered, 'attention_mask': rendered.ne(tokenizer.pad_token_id).long()}
    else:
        inputs = tokenizer(rendered, return_tensors='pt')
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

    start = time.perf_counter()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            enable_thinking=False,
            max_new_tokens=128,
            do_sample=False,
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    generated = outputs[0][inputs['input_ids'].shape[-1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    return text, elapsed_ms


def main() -> int:
    args = parse_args()
    adapter_dir = Path(args.adapter_dir)
    out_path = Path(args.out)
    errors: list[str] = []

    if not adapter_dir.exists():
        errors.append(f'Adapter dir not found: {adapter_dir}')
    if not Path(args.eval_file).exists():
        errors.append(f'Eval file not found: {args.eval_file}')
    if not Path(args.schema_file).exists():
        errors.append(f'Schema file not found: {args.schema_file}')
    if not (adapter_dir / 'adapter_model.safetensors').exists():
        errors.append('adapter_model.safetensors not found')
    if errors:
        result = make_phase_c_result(
            adapter_dir=str(adapter_dir),
            eval_file=args.eval_file,
            schema_file=args.schema_file,
            latency_budget_ms=args.latency_budget_ms,
            latencies_ms=[],
            outputs=[],
            errors=errors,
        )
        dump_json(out_path, result)
        print('PHASE_C_VERIFICATION_OK=0')
        return 1

    rows = load_jsonl(args.eval_file)[: args.max_samples]
    tokenizer, model = load_model_stack(adapter_dir, args.load_mode, args.device_preference)

    outputs: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    for idx, row in enumerate(rows, start=1):
        try:
            response, latency_ms = generate_one(tokenizer, model, row)
            outputs.append({
                'index': idx,
                'response': response,
                'latency_ms': latency_ms,
            })
            latencies_ms.append(latency_ms)
        except Exception as exc:
            errors.append(f'sample[{idx}] failed: {type(exc).__name__}: {exc}')

    result = make_phase_c_result(
        adapter_dir=str(adapter_dir),
        eval_file=args.eval_file,
        schema_file=args.schema_file,
        latency_budget_ms=args.latency_budget_ms,
        latencies_ms=latencies_ms,
        outputs=outputs,
        errors=errors,
    )
    dump_json(out_path, result)
    print(f"PHASE_C_VERIFICATION_OK={result['PHASE_C_VERIFICATION_OK']}")
    return 0 if result['PHASE_C_VERIFICATION_OK'] == 1 else 1


if __name__ == '__main__':
    raise SystemExit(main())
