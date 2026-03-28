from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.turboq.turboq_core_v1 import LloydMaxQuantizer, PolarQuant, QJLCorrector, TurboQuantKVCache


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def verify_turboq_structure() -> dict[str, Any]:
    report: list[dict[str, Any]] = []
    skipped_checks: list[dict[str, Any]] = []

    required_files = [
        'scripts/turboq/__init__.py',
        'scripts/turboq/turboq_core_v1.py',
        'scripts/turboq/turboq_butler_hook_v1.py',
        'scripts/turboq/turboq_server_v1.py',
        'scripts/turboq/turboq_mobile_v1.py',
        'scripts/turboq/turboq_benchmark_v1.py',
        'scripts/turboq/turboq_verify_v1.py',
        'scripts/turboq/turboq_run_dryrun_v1.sh',
        'tests/turboq/test_turboq_core.py',
        'tests/turboq/test_turboq_hook.py',
        'README_TURBOQ_KO.md',
    ]
    for rel_path in required_files:
        exists = (ROOT_DIR / rel_path).exists()
        report.append({'file': rel_path, 'ok': exists})
        print(f"[{'PASS' if exists else 'FAIL'}] {rel_path}")

    rng = np.random.default_rng(7)

    quantizer = LloydMaxQuantizer(bits=3)
    test_x = rng.standard_normal((5000, 128)).astype(np.float32)
    idx = quantizer.quantize(test_x)
    restored = quantizer.dequantize(idx)
    mse = float(np.mean((test_x - restored) ** 2))
    lloyd_ok = bool(mse < 0.1)
    report.append(
        {
            'check': 'lloyd_max_mse',
            'mse': mse,
            'ok': lloyd_ok,
            'fallback_used': quantizer.fallback_used,
        }
    )
    print(f"[{'PASS' if lloyd_ok else 'FAIL'}] Lloyd-Max MSE: {mse:.6f}")

    polar = PolarQuant(dim=128, bits=3)
    qjl = QJLCorrector(dim=128, n_bits=2048)
    kvcache = TurboQuantKVCache(head_dim=128, bits=3, qjl_n_bits=2048)
    biases: list[float] = []
    for _ in range(100):
        q_vec = rng.standard_normal(128).astype(np.float32)
        q_vec /= max(np.linalg.norm(q_vec), 1e-8)
        k_vec = rng.standard_normal(128).astype(np.float32)
        k_vec /= max(np.linalg.norm(k_vec), 1e-8)
        idx, norms = polar.compress(torch.tensor(k_vec).unsqueeze(0))
        k_approx = polar.decompress(idx, norms).numpy().reshape(-1)
        residual = k_vec - k_approx
        sign_bits = qjl.compress_residual(residual.reshape(1, -1)).reshape(-1)
        estimated = float(np.dot(q_vec, k_approx)) + qjl.correct_inner_product(q_vec, sign_bits)
        true_ip = float(np.dot(q_vec, k_vec))
        biases.append(abs(true_ip - estimated))
    mean_bias = float(np.mean(biases))
    bias_ok = bool(mean_bias < 0.05)
    report.append({'check': 'inner_product_bias', 'mean_bias': mean_bias, 'ok': bias_ok})
    print(f"[{'PASS' if bias_ok else 'FAIL'}] Inner-product bias: {mean_bias:.6f}")

    smoke_q = rng.standard_normal(128).astype(np.float32)
    smoke_q /= max(np.linalg.norm(smoke_q), 1e-8)
    smoke_k = torch.tensor(rng.standard_normal((1, 128)).astype(np.float32))
    smoke_payload = kvcache.compress_keys(smoke_k)
    attention_smoke = kvcache.approx_attention_score(smoke_q, smoke_payload, index=0)
    attention_ok = bool(np.isfinite(attention_smoke))
    report.append({'check': 'attention_smoke', 'score': float(attention_smoke), 'ok': attention_ok})
    print(f"[{'PASS' if attention_ok else 'FAIL'}] Attention smoke: {attention_smoke:.6f}")

    skipped_checks.append({'check': 'gpu_benchmark', 'reason': 'gpu_required'})
    skipped_checks.append({'check': 'mobile_real_device', 'reason': 'device_required'})

    all_pass = all(item.get('ok', False) for item in report)
    result = {
        'report': report,
        'all_pass': all_pass,
        'skipped_checks': skipped_checks,
        'fallback_used': quantizer.fallback_used,
        'notes': [
            'GPU measured_* fields remain empty until execution-team benchmark.',
            'This bundle is a research-faithful scaffold, not a claim of official Google code parity.',
        ],
    }
    write_json(ROOT_DIR / 'tmp/turboq_verify_result.json', result)
    if all_pass:
        print('TURBOQ_VERIFY_OK=1')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    _ = parser.parse_args()
    verify_turboq_structure()
