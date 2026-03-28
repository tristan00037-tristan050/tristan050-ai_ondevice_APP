from __future__ import annotations

import numpy as np
import torch

from scripts.turboq.turboq_core_v1 import LloydMaxQuantizer, PolarQuant, QJLCorrector, TurboQuantKVCache


def test_lloyd_max_quantizer_roundtrip_mse_under_budget() -> None:
    rng = np.random.default_rng(0)
    quantizer = LloydMaxQuantizer(bits=3)
    x = rng.standard_normal((2000, 128)).astype(np.float32)
    idx = quantizer.quantize(x)
    restored = quantizer.dequantize(idx)
    mse = float(np.mean((x - restored) ** 2))
    assert mse < 0.1


def test_force_fallback_keeps_centroids_deterministic() -> None:
    q1 = LloydMaxQuantizer(bits=3, force_fallback=True)
    q2 = LloydMaxQuantizer(bits=3, force_fallback=True)
    assert q1.fallback_used is True
    assert np.allclose(q1.centroids, q2.centroids)


def test_polar_quant_roundtrip_shape_and_dtype() -> None:
    rng = np.random.default_rng(1)
    polar = PolarQuant(dim=128, bits=3)
    x = torch.tensor(rng.standard_normal((4, 128)).astype(np.float32))
    idx, norms = polar.compress(x)
    restored = polar.decompress(idx, norms)
    assert idx.shape == (4, 128)
    assert norms.shape == (4, 1)
    assert tuple(restored.shape) == (4, 128)
    assert restored.dtype == torch.float32


def test_qjl_bias_is_reasonable_on_normalized_vectors() -> None:
    rng = np.random.default_rng(7)
    polar = PolarQuant(dim=128, bits=3)
    qjl = QJLCorrector(dim=128, n_bits=2048)
    biases = []
    for _ in range(32):
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
    assert float(np.mean(biases)) < 0.06


def test_turboquant_kvcache_summary_fields_exist() -> None:
    kv = TurboQuantKVCache(head_dim=128, bits=3)
    summary = kv.get_summary()
    assert summary['bits'] == 3
    assert summary['compression_ratio_target'] == 16 / 3
    assert summary['measured_compression_ratio'] is None
