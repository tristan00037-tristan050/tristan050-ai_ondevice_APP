#!/usr/bin/env python3
"""Verify AI-20 server-side training outputs.

Modes
- training-only: validates adapter artifacts only.
- complete: validates adapter artifacts and Phase C result evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RESULT_FILE = Path('tmp/ai20_server_postrun_result.json')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['training-only', 'complete'], required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--result-file')
    return parser.parse_args()


def load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def verify_training_only(output_dir: Path) -> dict[str, Any]:
    adapter_model = output_dir / 'adapter_model.safetensors'
    adapter_config = output_dir / 'adapter_config.json'
    metadata = output_dir / 'ai20_training_metadata.json'

    if not output_dir.exists():
        raise AssertionError(f'output dir missing: {output_dir}')
    if not adapter_model.exists():
        raise AssertionError(f'missing adapter model: {adapter_model}')
    if not adapter_config.exists():
        raise AssertionError(f'missing adapter config: {adapter_config}')

    config = load_json_if_exists(adapter_config) or {}
    base_model = config.get('base_model_name_or_path') or config.get('base_model_id')
    if base_model and base_model != 'Qwen/Qwen3-4B':
        raise AssertionError(f'unexpected base model in adapter config: {base_model}')

    return {
        'adapter_model': str(adapter_model),
        'adapter_config': str(adapter_config),
        'metadata_present': metadata.exists(),
        'TRAINING_ONLY_OK': 1,
    }


def verify_complete(output_dir: Path, result_file: Path | None) -> dict[str, Any]:
    training = verify_training_only(output_dir)
    if result_file is None:
        raise AssertionError('--result-file is required for mode=complete')
    result = load_json_if_exists(result_file)
    if result is None:
        raise AssertionError(f'phase c result missing: {result_file}')
    if result.get('PHASE_C_VERIFICATION_OK') != 1:
        raise AssertionError('PHASE_C_VERIFICATION_OK != 1')
    return {
        'training': training,
        'result_file': str(result_file),
        'PHASE_C_VERIFICATION_OK': 1,
        'COMPLETE_OK': 1,
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    result_file = Path(args.result_file) if args.result_file else None
    payload = {'mode': args.mode}
    try:
        if args.mode == 'training-only':
            payload['training_only'] = verify_training_only(output_dir)
            payload['AI20_POSTRUN_TRAINING_ONLY_OK'] = 1
            print('AI20_POSTRUN_TRAINING_ONLY_OK=1')
        else:
            payload['complete'] = verify_complete(output_dir, result_file)
            payload['AI20_POSTRUN_COMPLETE_OK'] = 1
            print('AI20_POSTRUN_COMPLETE_OK=1')
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return 0
    except Exception as exc:
        payload['error'] = f'{type(exc).__name__}: {exc}'
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print(f'[FAIL] {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
