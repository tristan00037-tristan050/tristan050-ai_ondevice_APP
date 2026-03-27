#!/usr/bin/env python3
"""Validate final completion evidence for AI-20 server handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RESULT_FILE = Path('tmp/ai20_completion_evidence_result.json')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--result-file', required=True)
    parser.add_argument('--output-dir', required=True)
    return parser.parse_args()


def ensure_real_artifacts(output_dir: Path) -> dict[str, str]:
    adapter_model = output_dir / 'adapter_model.safetensors'
    if not output_dir.exists():
        raise AssertionError(f'output dir missing: {output_dir}')
    if not adapter_model.exists():
        raise AssertionError(f'adapter_model.safetensors missing: {adapter_model}')
    forbidden = []
    for path in output_dir.rglob('*'):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered.startswith('sample_') or lowered.startswith('fake_'):
            forbidden.append(str(path))
    if forbidden:
        raise AssertionError(f'forbidden sample/fake result files present: {forbidden}')
    return {
        'adapter_model': str(adapter_model),
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    result_file = Path(args.result_file)
    payload = {}
    try:
        artifacts = ensure_real_artifacts(output_dir)
        if not result_file.exists():
            raise AssertionError(f'result file missing: {result_file}')
        result = json.loads(result_file.read_text(encoding='utf-8'))
        if result.get('PHASE_C_VERIFICATION_OK') != 1:
            raise AssertionError('PHASE_C_VERIFICATION_OK != 1')
        payload = {
            'output_dir': str(output_dir),
            'result_file': str(result_file),
            'artifacts': artifacts,
            'PHASE_C_VERIFICATION_OK': 1,
            'AI20_COMPLETION_EVIDENCE_OK': 1,
        }
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print('AI20_COMPLETION_EVIDENCE_OK=1')
        return 0
    except Exception as exc:
        payload = {
            'output_dir': str(output_dir),
            'result_file': str(result_file),
            'error': f'{type(exc).__name__}: {exc}',
            'AI20_COMPLETION_EVIDENCE_OK': 0,
        }
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESULT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print(f'[FAIL] {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
