"""Butler model-tier B-stage v2.2 product-pipeline benchmark.

This package is measurement-only. It must not alter the production model route,
activate cascade, or persist prompt/reference/draft text.
"""
from .contracts import (
    EnvironmentReceiptV22,
    FixtureManifestEntryV22,
    M3RoundVerdictV22,
    ProductSampleV22,
    QualityReceiptV22,
    SUBJECT_APP_SHA,
)
from .product_adapter import (
    Box3ExecutionBindings,
    ProductExecution,
    run_box1_rule_product,
    run_box3_primary_product,
    run_box3_same_run_cascade,
)

__all__ = [
    "SUBJECT_APP_SHA",
    "FixtureManifestEntryV22",
    "QualityReceiptV22",
    "ProductSampleV22",
    "EnvironmentReceiptV22",
    "M3RoundVerdictV22",
    "Box3ExecutionBindings",
    "ProductExecution",
    "run_box1_rule_product",
    "run_box3_primary_product",
    "run_box3_same_run_cascade",
]
