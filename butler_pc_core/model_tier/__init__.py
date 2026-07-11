"""Butler Phase 0 model-tier contracts and shadow-only observation."""

from .shadow_observer import (
    initialize_phase0_shadow,
    observe_box1_best_effort,
    observe_box3_best_effort,
    shutdown_phase0_shadow,
)

__all__ = [
    "initialize_phase0_shadow",
    "observe_box1_best_effort",
    "observe_box3_best_effort",
    "shutdown_phase0_shadow",
]
