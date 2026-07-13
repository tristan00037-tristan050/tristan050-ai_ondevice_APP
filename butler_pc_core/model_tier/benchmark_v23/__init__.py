"""Butler model-tier B-stage product-path benchmark v2.3."""

from .product_runtime import Box3ProductPipelineRuntime
from .runner import (
    build_counterbalanced_schedule,
    measure_dual_resident_pressure,
    run_cold_worker_handshake,
    run_product_matrix,
)
from .verifier import verify_samples_first

__all__ = [
    "Box3ProductPipelineRuntime",
    "build_counterbalanced_schedule",
    "run_product_matrix",
    "run_cold_worker_handshake",
    "measure_dual_resident_pressure",
    "verify_samples_first",
]
