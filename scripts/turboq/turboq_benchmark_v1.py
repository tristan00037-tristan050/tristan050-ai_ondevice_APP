from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


BUTLER_BENCHMARK_SCENARIOS = [
    {'name': '일상 대화 (10턴)', 'seq_len': 512, 'expected_accuracy': 0.99},
    {'name': '문서 요약 (A4 3장)', 'seq_len': 2048, 'expected_accuracy': 0.99},
    {'name': '법률 문서 분석', 'seq_len': 4096, 'expected_accuracy': 0.98},
    {'name': '장기 프로젝트 대화 (50턴)', 'seq_len': 8192, 'expected_accuracy': 0.97},
]


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def run_butler_benchmark_dryrun(scenarios: list[dict[str, Any]] = BUTLER_BENCHMARK_SCENARIOS) -> dict[str, Any]:
    results = []
    for scenario in scenarios:
        results.append(
            {
                'scenario': scenario['name'],
                'seq_len': scenario['seq_len'],
                'expected_compression_ratio': 16.0 / 3.0,
                'expected_accuracy': scenario['expected_accuracy'],
                'measured_compression_ratio': None,
                'measured_accuracy': None,
                'pass': None,
            }
        )
    payload = {
        'dry_run': True,
        'results': results,
        'note': 'measured_* values remain None until GPU/server/device execution is completed',
    }
    return payload


def run_butler_benchmark_gpu(
    model: Any,
    turboq_hook: Any,
    scenarios: list[dict[str, Any]] = BUTLER_BENCHMARK_SCENARIOS,
    *,
    measure_kv_memory: Callable[[Any, int, bool], float] | None = None,
    measure_attention_accuracy: Callable[[Any, Any, int], float] | None = None,
    output_path: str | Path = 'tmp/turboq_benchmark_result.json',
) -> dict[str, Any]:
    if measure_kv_memory is None or measure_attention_accuracy is None:
        raise ValueError('GPU benchmark requires injected measurement functions')

    results = []
    for scenario in scenarios:
        mem_before = measure_kv_memory(model, scenario['seq_len'], False)
        mem_after = measure_kv_memory(model, scenario['seq_len'], True)
        accuracy = measure_attention_accuracy(model, turboq_hook, scenario['seq_len'])
        results.append(
            {
                'scenario': scenario['name'],
                'seq_len': scenario['seq_len'],
                'measured_compression_ratio': None if mem_after == 0 else (mem_before / mem_after),
                'measured_accuracy': accuracy,
                'pass': bool(accuracy >= scenario['expected_accuracy']),
            }
        )

    payload = {'dry_run': False, 'results': results}
    write_json(output_path, payload)
    print('TURBOQ_BENCHMARK_OK=1')
    return payload
