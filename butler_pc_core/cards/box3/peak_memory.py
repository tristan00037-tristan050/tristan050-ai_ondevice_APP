from __future__ import annotations

import resource
import sys
import tracemalloc
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PeakMemoryMeasurement:
    result: object
    peak_memory_mb: float | None
    measurement_backend: str


def _rusage_rss_mb() -> float | None:
    """Per-process RSS via resource.getrusage. macOS reports bytes, Linux reports KB."""
    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        return None
    if rss <= 0:
        return None
    # macOS: ru_maxrss is in bytes; Linux: kilobytes. Normalize to MB.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(rss / divisor, 4)


def measure_peak_memory(callable_: Callable[[], T]) -> PeakMemoryMeasurement:
    """Measure *whole-process* peak memory before/after the callable.

    PR #777 정정 (2026-06-04): tracemalloc 은 Python 객체 메모리만 추적하므로 llama-cpp
    같은 C 확장 (libllama mmap 모델) 메모리를 측정하지 못해 1GB 모델 로드도 ~0.2 MB 로
    보고하던 결함. 본 정정에서 OS 수준 RSS 측정 (psutil / resource.getrusage) 우선,
    RSS 측정 불가 시 tracemalloc fallback 으로 격하 (정직 PARTIAL).

    측정 backend 우선순위:
      1) psutil.Process().memory_info().rss — Cross-platform 정확.
      2) resource.getrusage(RUSAGE_SELF).ru_maxrss — psutil 미설치 fallback.
      3) tracemalloc — Python-only fallback (정직: C 확장 미포함).
    """
    # Backend 1: psutil (선호).
    try:
        import psutil  # type: ignore

        proc = psutil.Process()
        before = proc.memory_info().rss
        result = callable_()
        after = proc.memory_info().rss
        peak = max(before, after)
        return PeakMemoryMeasurement(
            result=result,
            peak_memory_mb=round(peak / (1024 * 1024), 4),
            measurement_backend="psutil_rss",
        )
    except ImportError:
        pass

    # Backend 2: resource.getrusage (psutil 미설치 시).
    before_rss = _rusage_rss_mb()
    if before_rss is not None:
        result = callable_()
        after_rss = _rusage_rss_mb()
        peak_mb = max(before_rss, after_rss) if after_rss is not None else before_rss
        return PeakMemoryMeasurement(
            result=result,
            peak_memory_mb=peak_mb,
            measurement_backend="rusage_maxrss",
        )

    # Backend 3: tracemalloc fallback (정직: Python 객체만, PARTIAL classification).
    try:
        tracemalloc.start()
        result = callable_()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return PeakMemoryMeasurement(
            result=result,
            peak_memory_mb=round(peak / (1024 * 1024), 4),
            measurement_backend="tracemalloc_python_only",
        )
    except Exception:
        try:
            tracemalloc.stop()
        except Exception:
            pass
        result = callable_()
        return PeakMemoryMeasurement(
            result=result, peak_memory_mb=None, measurement_backend="unavailable"
        )
