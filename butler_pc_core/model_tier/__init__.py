"""Butler Phase 0 model-tier contracts and shadow-only observation."""

from .shadow_observer import (
    ShadowPreContext,
    complete_box1_shadow_best_effort,
    complete_box3_shadow_best_effort,
    initialize_phase0_shadow,
    observe_box1_best_effort,
    observe_box3_best_effort,
    phase0_shadow_status,
    prepare_box1_shadow_best_effort,
    prepare_box3_shadow_best_effort,
    shutdown_phase0_shadow,
)

__all__ = [
    "initialize_phase0_shadow",
    "ShadowPreContext",
    "prepare_box1_shadow_best_effort",
    "prepare_box3_shadow_best_effort",
    "complete_box1_shadow_best_effort",
    "complete_box3_shadow_best_effort",
    "observe_box1_best_effort",
    "observe_box3_best_effort",
    "phase0_shadow_status",
    "shutdown_phase0_shadow",
]
