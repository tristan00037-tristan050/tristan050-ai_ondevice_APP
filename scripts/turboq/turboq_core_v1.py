from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch


PRECOMPUTED_GAUSSIAN_CENTROIDS: dict[int, np.ndarray] = {
    2: np.array([-1.50957709, -0.45097730, 0.45527139, 1.51236265], dtype=np.float32),
    3: np.array(
        [-2.15918642, -1.35037991, -0.76213524, -0.25025676, 0.24065946, 0.75302232, 1.34015282, 2.15115913],
        dtype=np.float32,
    ),
    4: np.array(
        [
            -2.73031572,
            -2.05471380,
            -1.60269398,
            -1.24280609,
            -0.93055896,
            -0.64847152,
            -0.38410618,
            -0.13012466,
            0.12044168,
            0.37466204,
            0.63966227,
            0.92196434,
            1.23398338,
            1.59790877,
            2.05272637,
            2.71238954,
        ],
        dtype=np.float32,
    ),
}


@dataclass(slots=True)
class SafeResult:
    ok: bool
    reason_code: str | None
    payload: Any = None


def _truncated_normal_conditional_mean(a: float, b: float) -> float:
    try:
        from scipy.stats import norm
    except Exception as exc:  # pragma: no cover - imported above when available
        raise RuntimeError('scipy_unavailable') from exc

    phi_a = norm.pdf(a) if np.isfinite(a) else 0.0
    phi_b = norm.pdf(b) if np.isfinite(b) else 0.0
    Phi_a = norm.cdf(a) if np.isfinite(a) else 0.0
    Phi_b = norm.cdf(b) if np.isfinite(b) else 1.0
    denom = max(Phi_b - Phi_a, 1e-12)
    return float((phi_a - phi_b) / denom)


class LloydMaxQuantizer:
    """Scalar Lloyd-Max quantizer for approximately standard-normal coordinates.

    If scipy is unavailable, deterministic precomputed centroids are used and
    ``fallback_used`` is set to ``True``.
    """

    def __init__(self, bits: int = 3, *, force_fallback: bool = False):
        if bits < 1:
            raise ValueError('bits must be >= 1')
        self.bits = int(bits)
        self.n_centroids = 2 ** self.bits
        self.force_fallback = force_fallback
        self.fallback_used = False
        self.centroids = self._solve_lloyd_max().astype(np.float32)
        self.thresholds = ((self.centroids[:-1] + self.centroids[1:]) / 2.0).astype(np.float32)

    def _solve_lloyd_max(self) -> np.ndarray:
        if self.force_fallback:
            self.fallback_used = True
            return self._fallback_centroids()

        try:
            return self._compute_lloyd_max_scipy()
        except Exception:
            self.fallback_used = True
            return self._fallback_centroids()

    def _fallback_centroids(self) -> np.ndarray:
        if self.bits in PRECOMPUTED_GAUSSIAN_CENTROIDS:
            return PRECOMPUTED_GAUSSIAN_CENTROIDS[self.bits].copy()
        return self._compute_lloyd_max_numpy()

    def _compute_lloyd_max_numpy(self, iterations: int = 32, sample_size: int = 250_000) -> np.ndarray:
        rng = np.random.default_rng(0)
        samples = rng.standard_normal(sample_size).astype(np.float32)
        quantiles = np.linspace(0.0, 1.0, self.n_centroids + 2)[1:-1]
        centroids = np.quantile(samples, quantiles).astype(np.float32)
        for _ in range(iterations):
            thresholds = (centroids[:-1] + centroids[1:]) / 2.0
            indices = np.searchsorted(thresholds, samples, side='right')
            new_centroids = centroids.copy()
            for idx in range(self.n_centroids):
                bucket = samples[indices == idx]
                if bucket.size:
                    new_centroids[idx] = float(bucket.mean())
            if np.max(np.abs(new_centroids - centroids)) < 1e-6:
                centroids = new_centroids
                break
            centroids = new_centroids
        return centroids

    def _compute_lloyd_max_scipy(self, iterations: int = 50) -> np.ndarray:
        # Standard-normal centroid optimization. This avoids a hard scipy
        # dependency for dry-run because a deterministic fallback exists.
        import scipy  # noqa: F401  # imported only to validate availability

        centroids = PRECOMPUTED_GAUSSIAN_CENTROIDS.get(self.bits)
        if centroids is None:
            centroids = self._compute_lloyd_max_numpy(iterations=12, sample_size=100_000)
        else:
            centroids = centroids.copy()

        for _ in range(iterations):
            thresholds = (centroids[:-1] + centroids[1:]) / 2.0
            boundaries = np.concatenate(([-np.inf], thresholds, [np.inf])).astype(np.float64)
            new_centroids = np.empty_like(centroids)
            for idx in range(self.n_centroids):
                new_centroids[idx] = _truncated_normal_conditional_mean(boundaries[idx], boundaries[idx + 1])
            if np.max(np.abs(new_centroids - centroids)) < 1e-7:
                centroids = new_centroids.astype(np.float32)
                break
            centroids = new_centroids.astype(np.float32)
        return centroids

    def quantize(self, x: np.ndarray) -> np.ndarray:
        x_np = np.asarray(x, dtype=np.float32)
        idx = np.searchsorted(self.thresholds, x_np, side='right').astype(np.uint8)
        return idx

    def dequantize(self, idx: np.ndarray) -> np.ndarray:
        idx_np = np.asarray(idx)
        idx_clipped = np.clip(idx_np.astype(np.int64), 0, self.n_centroids - 1)
        return self.centroids[idx_clipped]


class PolarQuant:
    """Stage 1: random orthogonal rotation + scalar quantization."""

    def __init__(self, dim: int, bits: int = 3, seed: int = 42, *, force_fallback: bool = False):
        if dim <= 0:
            raise ValueError('dim must be positive')
        self.dim = int(dim)
        self.bits = int(bits)
        rng = np.random.default_rng(seed)
        gaussian = rng.standard_normal((self.dim, self.dim)).astype(np.float32)
        self.Pi, _ = np.linalg.qr(gaussian)
        self.quantizer = LloydMaxQuantizer(bits=self.bits, force_fallback=force_fallback)
        self.scale = math.sqrt(self.dim)

    def compress(self, x: torch.Tensor) -> tuple[np.ndarray, np.ndarray]:
        if x.shape[-1] != self.dim:
            raise ValueError(f'expected trailing dimension {self.dim}, got {x.shape[-1]}')
        x_np = x.detach().float().cpu().numpy().reshape(-1, self.dim)
        norms = np.linalg.norm(x_np, axis=-1, keepdims=True).astype(np.float32)
        norms = np.maximum(norms, 1e-8)
        unit = x_np / norms
        rotated = unit @ self.Pi.T
        rotated_scaled = rotated * self.scale
        idx = self.quantizer.quantize(rotated_scaled).reshape(x_np.shape)
        return idx, norms

    def compress_safe(self, x: torch.Tensor) -> SafeResult:
        try:
            idx, norms = self.compress(x)
            return SafeResult(ok=True, reason_code=None, payload={'idx': idx, 'norms': norms})
        except Exception as exc:
            return SafeResult(ok=False, reason_code=f'compress_error:{type(exc).__name__}', payload=None)

    def decompress(self, idx: np.ndarray, norms: np.ndarray) -> torch.Tensor:
        idx_np = np.asarray(idx).reshape(-1, self.dim)
        norms_np = np.asarray(norms, dtype=np.float32).reshape(-1, 1)
        rotated_scaled = self.quantizer.dequantize(idx_np)
        rotated = rotated_scaled / self.scale
        unit = rotated @ self.Pi
        unit_norm = np.linalg.norm(unit, axis=-1, keepdims=True).astype(np.float32)
        unit_norm = np.maximum(unit_norm, 1e-8)
        unit = unit / unit_norm
        restored = (unit * norms_np).astype(np.float32)
        return torch.from_numpy(restored)

    def decompress_safe(self, idx: np.ndarray, norms: np.ndarray) -> SafeResult:
        try:
            tensor = self.decompress(idx, norms)
            return SafeResult(ok=True, reason_code=None, payload=tensor)
        except Exception as exc:
            return SafeResult(ok=False, reason_code=f'decompress_error:{type(exc).__name__}', payload=None)


class QJLCorrector:
    """Stage 2: 1-bit residual correction using a sign sketch.

    This is an engineering scaffold. It uses a deterministic Rademacher matrix
    and exposes an unbiased sign-estimator style correction path suitable for
    dry-run verification. Real serving benchmarks must still be measured on
    Butler hardware.
    """

    def __init__(self, dim: int, n_bits: int = 2048, seed: int = 123):
        if dim <= 0:
            raise ValueError('dim must be positive')
        if n_bits <= 0:
            raise ValueError('n_bits must be positive')
        self.dim = int(dim)
        self.n_bits = int(n_bits)
        rng = np.random.default_rng(seed)
        self.S = rng.choice([-1.0, 1.0], size=(self.n_bits, self.dim)).astype(np.float32)

    def compress_residual(self, residual: np.ndarray) -> np.ndarray:
        residual_np = np.asarray(residual, dtype=np.float32).reshape(-1, self.dim)
        projections = residual_np @ self.S.T
        sign_bits = np.sign(projections).astype(np.int8)
        sign_bits[sign_bits == 0] = 1
        return sign_bits

    def correct_inner_product(self, q: np.ndarray, sign_bits: np.ndarray) -> float:
        q_np = np.asarray(q, dtype=np.float32).reshape(-1)
        signs_np = np.asarray(sign_bits, dtype=np.float32).reshape(-1)
        if q_np.size != self.dim:
            raise ValueError(f'query size must be {self.dim}, got {q_np.size}')
        if signs_np.size != self.n_bits:
            raise ValueError(f'sign_bits size must be {self.n_bits}, got {signs_np.size}')
        return float((1.0 / self.n_bits) * np.dot(self.S @ q_np, signs_np))


class TurboQuantKVCache:
    """Butler KV cache compression interface.

    This class intentionally separates expected ratios from measured metrics.
    Until GPU/server/device runs are completed, only target ratios are exposed.
    """

    def __init__(self, head_dim: int, bits: int = 3, seed: int = 42, qjl_n_bits: int = 2048):
        self.head_dim = int(head_dim)
        self.bits = int(bits)
        self.seed = int(seed)
        self.qjl_n_bits = int(qjl_n_bits)
        self.polar = PolarQuant(head_dim, bits=bits, seed=seed)
        self.qjl = QJLCorrector(head_dim, n_bits=qjl_n_bits, seed=seed + 81)

    def compress_keys(self, K: torch.Tensor) -> dict[str, Any]:
        try:
            if K.shape[-1] != self.head_dim:
                return {
                    'ok': False,
                    'reason_code': 'invalid_head_dim',
                    'shape': tuple(K.shape),
                    'bits': self.bits,
                }
            flat = K.detach().float().cpu().reshape(-1, self.head_dim)
            idx, norms = self.polar.compress(flat)
            restored = self.polar.decompress(idx, norms).numpy()
            residual = flat.numpy() - restored
            sign_bits = self.qjl.compress_residual(residual)
            return {
                'ok': True,
                'reason_code': None,
                'idx': idx,
                'norms': norms,
                'sign_bits': sign_bits,
                'shape': tuple(K.shape),
                'bits': self.bits,
                'qjl_n_bits': self.qjl_n_bits,
                'fallback_used': self.polar.quantizer.fallback_used,
            }
        except Exception as exc:
            return {
                'ok': False,
                'reason_code': f'compress_keys_error:{type(exc).__name__}',
                'shape': tuple(K.shape),
                'bits': self.bits,
            }

    def compress_values(self, V: torch.Tensor) -> dict[str, Any]:
        try:
            if V.shape[-1] != self.head_dim:
                return {
                    'ok': False,
                    'reason_code': 'invalid_head_dim',
                    'shape': tuple(V.shape),
                    'bits': self.bits,
                }
            flat = V.detach().float().cpu().reshape(-1, self.head_dim)
            idx, norms = self.polar.compress(flat)
            return {
                'ok': True,
                'reason_code': None,
                'idx': idx,
                'norms': norms,
                'shape': tuple(V.shape),
                'bits': self.bits,
                'fallback_used': self.polar.quantizer.fallback_used,
            }
        except Exception as exc:
            return {
                'ok': False,
                'reason_code': f'compress_values_error:{type(exc).__name__}',
                'shape': tuple(V.shape),
                'bits': self.bits,
            }

    def approx_attention_score(self, query: np.ndarray, compressed_key: dict[str, Any], index: int = 0) -> float:
        if not compressed_key.get('ok', False):
            raise ValueError(f"compressed_key is not usable: {compressed_key.get('reason_code')}")
        idx = compressed_key['idx'][index:index + 1]
        norms = compressed_key['norms'][index:index + 1]
        restored = self.polar.decompress(idx, norms).numpy().reshape(-1)
        sign_bits = compressed_key['sign_bits'][index]
        q_vec = np.asarray(query, dtype=np.float32).reshape(-1)
        return float(np.dot(q_vec, restored) + self.qjl.correct_inner_product(q_vec, sign_bits))

    def get_summary(self) -> dict[str, Any]:
        return {
            'bits': self.bits,
            'compression_ratio_target': 16.0 / float(self.bits),
            'fallback_used': self.polar.quantizer.fallback_used,
            'qjl_n_bits': self.qjl_n_bits,
            'implementation_mode': 'research_faithful_scaffold',
            'measured_compression_ratio': None,
            'measured_accuracy': None,
        }
