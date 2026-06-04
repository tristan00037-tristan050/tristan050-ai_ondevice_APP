from __future__ import annotations

import tracemalloc
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PeakMemoryMeasurement:
    result: object
    peak_memory_mb: float | None
    measurement_backend: str


def measure_peak_memory(callable_: Callable[[], T]) -> PeakMemoryMeasurement:
    """Measure Python-level peak memory. Platform RSS samplers can replace this later.

    Peak memory is required by the v1.2 directive. If tracemalloc cannot report, the
    caller must classify the run as PARTIAL rather than PASS.
    """
    try:
        tracemalloc.start()
        result = callable_()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return PeakMemoryMeasurement(result=result, peak_memory_mb=round(peak / (1024 * 1024), 4), measurement_backend="tracemalloc")
    except Exception:
        try:
            tracemalloc.stop()
        except Exception:
            pass
        result = callable_()
        return PeakMemoryMeasurement(result=result, peak_memory_mb=None, measurement_backend="unavailable")
