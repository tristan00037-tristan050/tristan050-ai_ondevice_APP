"""Tail-latency and determinism benchmark for v3.2 classification."""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from butler_pc_core.accounting.classify.models import CanonicalTransactionV2, stable_digest
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.port import PolicyPort


PortFactory = Callable[[CanonicalTransactionV2], PolicyPort]


@dataclass(frozen=True, slots=True)
class BenchmarkReceipt:
    samples: int
    warmup_iterations: int
    measured_iterations: int
    p50_us: int
    p90_us: int
    p95_us: int
    p99_us: int
    mean_us: int
    stdev_us: int
    max_us: int
    deterministic_replay: bool
    failure_count: int
    classifier_contract_version: str
    input_set_digest: str

    def to_safe_dict(self) -> dict[str, int | str | bool]:
        return {
            "schema_version": "butler.box5.stage3_benchmark.v3.2",
            "samples": self.samples,
            "warmup_iterations": self.warmup_iterations,
            "measured_iterations": self.measured_iterations,
            "p50_us": self.p50_us,
            "p90_us": self.p90_us,
            "p95_us": self.p95_us,
            "p99_us": self.p99_us,
            "mean_us": self.mean_us,
            "stdev_us": self.stdev_us,
            "max_us": self.max_us,
            "deterministic_replay": self.deterministic_replay,
            "failure_count": self.failure_count,
            "classifier_contract_version": self.classifier_contract_version,
            "input_set_digest": self.input_set_digest,
        }


def _percentile(values: Sequence[int], fraction: float) -> int:
    return values[max(0, math.ceil(fraction * len(values)) - 1)]


def run_classifier_benchmark(
    classifier: Stage3Classifier,
    transactions: Sequence[CanonicalTransactionV2],
    *,
    port_factory: PortFactory,
    warmup_iterations: int = 2,
    measured_iterations: int = 10,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> BenchmarkReceipt:
    if not transactions:
        raise ValueError("BENCHMARK_TRANSACTIONS_REQUIRED")
    if not 0 <= warmup_iterations <= 100 or not 1 <= measured_iterations <= 10_000:
        raise ValueError("BENCHMARK_ITERATIONS_INVALID")
    for _ in range(warmup_iterations):
        for transaction in transactions:
            classifier.classify(transaction, port_factory(transaction))
    baselines: dict[str, str] = {}
    durations: list[int] = []
    failures = 0
    deterministic = True
    for _ in range(measured_iterations):
        for transaction in transactions:
            started = clock_ns()
            try:
                draft = classifier.classify(transaction, port_factory(transaction))
                prior = baselines.setdefault(transaction.transaction_digest, draft.semantic_digest)
                deterministic = deterministic and prior == draft.semantic_digest
            except Exception:
                failures += 1
            finally:
                durations.append(max(1, math.ceil(max(0, clock_ns() - started) / 1_000)))
    ordered = sorted(durations)
    return BenchmarkReceipt(
        samples=len(ordered),
        warmup_iterations=warmup_iterations,
        measured_iterations=measured_iterations,
        p50_us=_percentile(ordered, 0.50),
        p90_us=_percentile(ordered, 0.90),
        p95_us=_percentile(ordered, 0.95),
        p99_us=_percentile(ordered, 0.99),
        mean_us=round(statistics.fmean(ordered)),
        stdev_us=round(statistics.pstdev(ordered)),
        max_us=ordered[-1],
        deterministic_replay=deterministic and failures == 0,
        failure_count=failures,
        classifier_contract_version=classifier.CONTRACT_VERSION,
        input_set_digest=stable_digest([tx.transaction_digest for tx in transactions]),
    )
