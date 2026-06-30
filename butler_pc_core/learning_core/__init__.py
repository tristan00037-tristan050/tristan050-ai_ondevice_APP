"""Digest-only integrated learning core for Butler.

This package intentionally does not modify the existing connect_loop
usage_log/learning_event path. It evaluates separately contracted integrated
learning candidates and can only produce review artifacts or index candidates.
"""
from .contracts import GateResult, IntegratedLearningError, stable_json_digest
from .gate import UnifiedLearningIntakeGate
from .adapter_registry import AdapterRegistry, register_default_adapters

__all__ = [
    "AdapterRegistry",
    "GateResult",
    "IntegratedLearningError",
    "UnifiedLearningIntakeGate",
    "register_default_adapters",
    "stable_json_digest",
]
