"""Area-B evaluation utilities for the v3.2 classifier."""

from .benchmark import BenchmarkReceipt, run_classifier_benchmark
from .regression import (
    ExpectedDraft,
    RegressionReceipt,
    RegressionViolation,
    evaluate_regression,
    prove_zero_regression,
)

__all__ = [
    "BenchmarkReceipt",
    "ExpectedDraft",
    "RegressionReceipt",
    "RegressionViolation",
    "evaluate_regression",
    "prove_zero_regression",
    "run_classifier_benchmark",
]
