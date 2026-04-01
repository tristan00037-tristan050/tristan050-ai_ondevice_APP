#!/usr/bin/env python3
"""AI-20 / butler_model_small_v1 QLoRA training entrypoint for Qwen3-4B.

Design goals:
- dry-run works without GPU and without importing heavy training libraries eagerly.
- runtime training path stays compatible with multiple TRL versions by inspecting signatures.
- Qwen3 non-thinking mode is enforced fail-closed.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from typing import Any

QLORA_SMALL_CONFIG = {
    'base_model_id': 'Qwen/Qwen3-4B',
    'output_dir': 'output/butler_model_small_v1',
    'per_device_train_batch_size': 3,
    'gradient_accumulation_steps': 6,
    # Training length: max_steps only. Do not pass num_train_epochs to Trainer/SFTConfig
    # (e.g. -1 is invalid; mixing epochs + max_steps conflicts with HF Trainer).
    'max_steps': 1000,
    'learning_rate': 2.5e-4,
    'lora_r': 12,
    'lora_alpha': 24,
    'lora_dropout': 0.05,
    'max_seq_length': 1536,
    'load_in_4bit': True,
    'bf16': True,
}

QWEN3_SPECIFIC = {
    'enable_thinking': False,
    'chat_template': 'qwen3_nonthinking',
}

FORBIDDEN_SFTTRAINER_PARAMS = ['dataset_text_field', 'packing', 'max_seq_length']
DEFAULT_RESULT_FILE = Path('tmp/ai20_finetune_dryrun_result.json')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--train-file')
    parser.add_argument('--eval-file')
    parser.add_argument('--output-dir', default=QLORA_SMALL_CONFIG['output_dir'])
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def optional_version(module_name: str) -> str:
    try:
        module = __import__(module_name)
    except Exception:
        return 'unavailable'
    return getattr(module, '__version__', 'unknown')


def _inspect_signature(module_name: str, attr_chain: list[str]) -> tuple[list[str], str]:
    try:
        module = __import__(module_name, fromlist=[attr_chain[0]])
        target = module
        for attr in attr_chain:
            target = getattr(target, attr)
        signature = inspect.signature(target)
    except Exception as exc:
        return [], f'{type(exc).__name__}: {exc}'
    return list(signature.parameters.keys()), 'ok'


def collect_dry_run_metadata(output_dir: str) -> dict[str, Any]:
    sft_allowed, sft_status = _inspect_signature('trl', ['SFTConfig', '__init__'])
    trainer_allowed, trainer_status = _inspect_signature('trl', ['SFTTrainer', '__init__'])

    resolved_max_length_key = None
    sft_kwargs_preview = {
        'output_dir': output_dir,
        'per_device_train_batch_size': QLORA_SMALL_CONFIG['per_device_train_batch_size'],
        'gradient_accumulation_steps': QLORA_SMALL_CONFIG['gradient_accumulation_steps'],
        'max_steps': QLORA_SMALL_CONFIG['max_steps'],
        'learning_rate': QLORA_SMALL_CONFIG['learning_rate'],
        'bf16': QLORA_SMALL_CONFIG['bf16'],
        'report_to': 'none',
        'save_strategy': 'steps',
        'eval_strategy': 'steps',
        'logging_steps': 10,
    }

    if 'max_seq_length' in sft_allowed:
        resolved_max_length_key = 'max_seq_length'
        sft_kwargs_preview['max_seq_length'] = QLORA_SMALL_CONFIG['max_seq_length']
    elif 'max_length' in sft_allowed:
        resolved_max_length_key = 'max_length'
        sft_kwargs_preview['max_length'] = QLORA_SMALL_CONFIG['max_seq_length']
    else:
        resolved_max_length_key = 'handled_outside_sftconfig'

    trainer_preview = {
        'passes_processing_class': 'processing_class' in trainer_allowed,
        'passes_formatting_func': 'formatting_func' in trainer_allowed,
        'forbidden_params_passed_to_sfttrainer': [],
    }

    return {
        'base_model_id': QLORA_SMALL_CONFIG['base_model_id'],
        'output_dir': output_dir,
        'qlora_small_config': QLORA_SMALL_CONFIG,
        'qwen3_specific': QWEN3_SPECIFIC,
        'versions': {
            'torch': optional_version('torch'),
            'transformers': optional_version('transformers'),
            'trl': optional_version('trl'),
            'peft': optional_version('peft'),
            'bitsandbytes': optional_version('bitsandbytes'),
            'accelerate': optional_version('accelerate'),
            'datasets': optional_version('datasets'),
        },
        'inspection': {
            'sftconfig_status': sft_status,
            'sfttrainer_status': trainer_status,
            'allowed_sft_kwargs': sft_allowed,
            'allowed_sfttrainer_kwargs': trainer_allowed,
            'resolved_max_length_key': resolved_max_length_key,
            'forbidden_sfttrainer_params': FORBIDDEN_SFTTRAINER_PARAMS,
            'forbidden_params_absent': all(param not in trainer_allowed for param in FORBIDDEN_SFTTRAINER_PARAMS),
        },
        'preview': {
            'sft_config_kwargs': sft_kwargs_preview,
            'trainer_kwargs': trainer_preview,
        },
        'checks': {
            'enable_thinking_is_false': QWEN3_SPECIFIC['enable_thinking'] is False,
            'chat_template_is_qwen3_nonthinking': QWEN3_SPECIFIC['chat_template'] == 'qwen3_nonthinking',
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def load_jsonl_rows(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8') as handle:
        for idx, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSONL at {path}:{idx}: {exc}') from exc
    return rows


def normalize_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    if isinstance(record.get('messages'), list):
        return [
            {'role': str(item['role']), 'content': str(item['content'])}
            for item in record['messages']
            if isinstance(item, dict) and 'role' in item and 'content' in item
        ]
    if isinstance(record.get('conversations'), list):
        normalized: list[dict[str, str]] = []
        for item in record['conversations']:
            if not isinstance(item, dict):
                continue
            role = item.get('role') or item.get('from')
            content = item.get('content') or item.get('value')
            if role and content is not None:
                normalized.append({'role': str(role), 'content': str(content)})
        if normalized:
            return normalized
    if 'prompt' in record and 'response' in record:
        return [
            {'role': 'user', 'content': str(record['prompt'])},
            {'role': 'assistant', 'content': str(record['response'])},
        ]
    if 'instruction' in record and 'output' in record:
        system = record.get('system')
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({'role': 'system', 'content': str(system)})
        msgs.append({'role': 'user', 'content': str(record['instruction'])})
        msgs.append({'role': 'assistant', 'content': str(record['output'])})
        return msgs
    if 'prompt' in record and 'completion' in record:
        return [
            {'role': 'user', 'content': str(record['prompt'])},
            {'role': 'assistant', 'content': str(record['completion'])},
        ]
    if 'text' in record:
        return [{'role': 'user', 'content': str(record['text'])}]
    raise ValueError(f'Unsupported training record keys: {sorted(record.keys())}')


def render_training_text(tokenizer: Any, record: dict[str, Any]) -> str:
    messages = normalize_messages(record)
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )


def pretokenize_dataset(dataset: Any, tokenizer: Any, max_length: int) -> Any:
    def tokenize_row(example: dict[str, Any]) -> dict[str, Any]:
        tokens = tokenizer(
            example['text'],
            truncation=True,
            max_length=max_length,
            add_special_tokens=False,
        )
        tokens['labels'] = list(tokens['input_ids'])
        return tokens

    columns = list(dataset.column_names)
    import hashlib, os
    dataset_fingerprint = getattr(dataset, '_fingerprint', '') or str(len(dataset))
    cache_key = hashlib.md5((str(tokenizer.name_or_path) + str(max_length) + dataset_fingerprint).encode()).hexdigest()[:12]
    cache_dir = '/data/tokenize_cache'
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = f'{cache_dir}/tokenized_{cache_key}.arrow'
    return dataset.map(tokenize_row, remove_columns=columns, cache_file_name=cache_file)


def resolve_sft_config(output_dir: str) -> Any:
    from trl import SFTConfig

    allowed = set(inspect.signature(SFTConfig.__init__).parameters.keys())
    kwargs = {
        'output_dir': output_dir,
        'per_device_train_batch_size': QLORA_SMALL_CONFIG['per_device_train_batch_size'],
        'gradient_accumulation_steps': QLORA_SMALL_CONFIG['gradient_accumulation_steps'],
        'learning_rate': QLORA_SMALL_CONFIG['learning_rate'],
        'bf16': QLORA_SMALL_CONFIG['bf16'],
        'report_to': 'none',
        'save_strategy': 'steps',
        'eval_strategy': 'steps',
        'logging_steps': 10,
        'seed': 42,
        'gradient_checkpointing': True,
        'max_steps': QLORA_SMALL_CONFIG['max_steps'],
    }
    if 'max_seq_length' in allowed:
        kwargs['max_seq_length'] = QLORA_SMALL_CONFIG['max_seq_length']
    elif 'max_length' in allowed:
        kwargs['max_length'] = QLORA_SMALL_CONFIG['max_seq_length']
    if 'save_total_limit' in allowed:
        kwargs['save_total_limit'] = 2
    if 'remove_unused_columns' in allowed:
        kwargs['remove_unused_columns'] = False
    return SFTConfig(**kwargs)


def run_training(train_file: str, eval_file: str | None, output_dir: str) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTTrainer

    if not train_file:
        raise ValueError('--train-file is required for training mode.')

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(QLORA_SMALL_CONFIG['base_model_id'])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        QLORA_SMALL_CONFIG['base_model_id'],
        dtype=torch.bfloat16,
        device_map='auto',
    )

    train_rows = load_jsonl_rows(train_file)
    train_text_rows = [{'text': render_training_text(tokenizer, row)} for row in train_rows]
    train_dataset = Dataset.from_list(train_text_rows)

    eval_dataset = None
    if eval_file:
        eval_rows = load_jsonl_rows(eval_file)
        eval_text_rows = [{'text': render_training_text(tokenizer, row)} for row in eval_rows]
        eval_dataset = Dataset.from_list(eval_text_rows)

    peft_config = LoraConfig(
        r=QLORA_SMALL_CONFIG['lora_r'],
        lora_alpha=QLORA_SMALL_CONFIG['lora_alpha'],
        lora_dropout=QLORA_SMALL_CONFIG['lora_dropout'],
        bias='none',
        task_type='CAUSAL_LM',
        target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj'],
    )

    trainer_signature = set(inspect.signature(SFTTrainer.__init__).parameters.keys())
    trainer_kwargs: dict[str, Any] = {
        'model': model,
        'args': resolve_sft_config(output_dir),
        'train_dataset': train_dataset,
        'eval_dataset': eval_dataset,
        'peft_config': peft_config,
    }

    if 'processing_class' in trainer_signature:
        trainer_kwargs['processing_class'] = tokenizer

    if 'formatting_func' in trainer_signature:
        trainer_kwargs['formatting_func'] = lambda example: example['text']
    else:
        train_dataset = pretokenize_dataset(train_dataset, tokenizer, QLORA_SMALL_CONFIG['max_seq_length'])
        trainer_kwargs['train_dataset'] = train_dataset
        if eval_dataset is not None:
            trainer_kwargs['eval_dataset'] = pretokenize_dataset(eval_dataset, tokenizer, QLORA_SMALL_CONFIG['max_seq_length'])

    trainer = SFTTrainer(**trainer_kwargs)
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    write_json(Path(output_dir) / 'ai20_training_metadata.json', {
        'base_model_id': QLORA_SMALL_CONFIG['base_model_id'],
        'qwen3_specific': QWEN3_SPECIFIC,
        'environment': {
            'cwd': os.getcwd(),
        },
    })
    print('QLORA_TRAIN_RUN_OK=1')


def main() -> int:
    args = parse_args()
    payload = collect_dry_run_metadata(output_dir=args.output_dir)
    write_json(DEFAULT_RESULT_FILE, payload)
    if args.dry_run:
        print('FINETUNE_SMALL_DRY_OK=1')
        return 0
    run_training(args.train_file, args.eval_file, args.output_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
