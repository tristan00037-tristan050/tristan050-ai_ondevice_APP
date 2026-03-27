#!/usr/bin/env python3
"""Validate AI-20 Qwen3-4B training bundle structure and execution readiness."""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
from pathlib import Path
from typing import Any

RESULT_FILE = Path('tmp/ai20_bundle_structure_result.json')
REQUIRED_POLICY_KEYWORDS = [
    '안 됩니다', '안됩니다', '불가', '금지', '위반', '주의',
    '허용되지', '허용되지 않습니다', '승인 절차',
    'Sorry', 'cannot', "can't", 'not allowed',
    'comply', 'prohibited', 'not permitted',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-dir', required=True)
    parser.add_argument('--train-file')
    parser.add_argument('--eval-file')
    parser.add_argument('--dry-run', action='store_true')
    return parser.parse_args()


def extract_literal_dict(source_path: Path, variable_name: str) -> dict[str, Any]:
    module = ast.parse(source_path.read_text(encoding='utf-8'))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == variable_name:
                    return ast.literal_eval(node.value)
    raise ValueError(f'{variable_name} not found in {source_path}')


def assert_condition(condition: bool, label: str, report: list[dict[str, Any]]) -> None:
    entry = {'label': label, 'ok': bool(condition)}
    report.append(entry)
    prefix = '[PASS]' if condition else '[FAIL]'
    print(f'{prefix} {label}')
    if not condition:
        raise AssertionError(label)


def count_jsonl_lines(path: Path) -> int:
    count = 0
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def verify_structure(repo_dir: Path) -> dict[str, Any]:
    finetune_path = repo_dir / 'scripts/ai/finetune_qlora_small_v1.py'
    phase_c_shared_path = repo_dir / 'scripts/ai/phase_c_shared.py'
    report: list[dict[str, Any]] = []

    qlora_config = extract_literal_dict(finetune_path, 'QLORA_SMALL_CONFIG')
    qwen3_specific = extract_literal_dict(finetune_path, 'QWEN3_SPECIFIC')
    finetune_source = finetune_path.read_text(encoding='utf-8')
    phase_c_source = phase_c_shared_path.read_text(encoding='utf-8')

    assert_condition(qlora_config['base_model_id'] == 'Qwen/Qwen3-4B', '베이스 모델: Qwen/Qwen3-4B', report)
    assert_condition(
        qlora_config['lora_r'] == 12 and qlora_config['lora_alpha'] == 24 and qlora_config['max_seq_length'] == 1536,
        'lora_r=12, lora_alpha=24, max_seq_length=1536',
        report,
    )
    assert_condition(qwen3_specific['enable_thinking'] is False, 'enable_thinking=False', report)
    assert_condition(qwen3_specific['chat_template'] == 'qwen3_nonthinking', 'chat_template=qwen3_nonthinking', report)

    trainer_call_pattern = re.compile(r'SFTTrainer\((.*?)\)', re.DOTALL)
    trainer_calls = trainer_call_pattern.findall(finetune_source)
    forbidden_absent = True
    for trainer_call in trainer_calls:
        if 'dataset_text_field' in trainer_call or 'packing=' in trainer_call or 'max_seq_length=' in trainer_call:
            forbidden_absent = False
            break
    assert_condition(forbidden_absent, 'SFTTrainer 제거 파라미터 없음', report)

    keyword_missing = [kw for kw in REQUIRED_POLICY_KEYWORDS if kw not in phase_c_source]
    assert_condition(not keyword_missing, 'SAFE_POLICY_KEYWORDS_KO 영어 키워드 포함', report)

    return {
        'report': report,
        'qlora_small_config': qlora_config,
        'qwen3_specific': qwen3_specific,
        'keyword_missing': keyword_missing,
    }


def verify_ready(repo_dir: Path, train_file: Path, eval_file: Path) -> dict[str, Any]:
    output_dir = repo_dir / 'output' / 'butler_model_small_v1'
    output_dir.mkdir(parents=True, exist_ok=True)
    ready: dict[str, Any] = {}

    if not train_file.exists():
        raise AssertionError(f'train file missing: {train_file}')
    if not eval_file.exists():
        raise AssertionError(f'eval file missing: {eval_file}')

    train_lines = count_jsonl_lines(train_file)
    eval_lines = count_jsonl_lines(eval_file)
    if train_lines < 100:
        raise AssertionError(f'train file must have at least 100 lines, found {train_lines}')
    if eval_lines < 10:
        raise AssertionError(f'eval file must have at least 10 lines, found {eval_lines}')
    if not os.access(output_dir, os.W_OK):
        raise AssertionError(f'output dir not writable: {output_dir}')

    ready['train_file'] = str(train_file)
    ready['eval_file'] = str(eval_file)
    ready['train_lines'] = train_lines
    ready['eval_lines'] = eval_lines
    ready['output_dir'] = str(output_dir)
    ready['output_dir_writable'] = True
    return ready


def main() -> int:
    args = parse_args()
    repo_dir = Path(args.repo_dir).resolve()
    result_path = repo_dir / RESULT_FILE
    result_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        structure = verify_structure(repo_dir)
        result: dict[str, Any] = {
            'structure': structure,
            'AI20_BUNDLE_STRUCTURE_OK': 1,
        }
        if not args.dry_run:
            if not args.train_file or not args.eval_file:
                raise AssertionError('--train-file and --eval-file are required unless --dry-run is used')
            ready = verify_ready(repo_dir, Path(args.train_file), Path(args.eval_file))
            result['ready'] = ready
            result['AI20_BUNDLE_READY'] = 1
            print('AI20_BUNDLE_READY=1')
        else:
            print('AI20_BUNDLE_STRUCTURE_OK=1')

        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return 0
    except Exception as exc:
        result = {
            'AI20_BUNDLE_STRUCTURE_OK': 0,
            'AI20_BUNDLE_READY': 0,
            'error': f'{type(exc).__name__}: {exc}',
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print(f'[FAIL] {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
