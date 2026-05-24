from __future__ import annotations

import time
from statistics import median
from typing import Callable, Iterable, List


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * q))))
    return sorted_values[idx]


def measure_ms(fn: Callable[[], object], iterations: int = 100) -> dict[str, float]:
    samples: List[float] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        fn()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
        samples.append(elapsed_ms)
    return {
        "count": len(samples),
        "p50_ms": round(percentile(samples, 0.50), 4),
        "p95_ms": round(percentile(samples, 0.95), 4),
        "p99_ms": round(percentile(samples, 0.99), 4),
        "max_ms": round(max(samples), 4),
    }
