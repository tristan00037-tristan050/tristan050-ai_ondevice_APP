"""Card 5 v3 제품 통합 불변량 검증."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Invariants:
    base_model_changed: bool = False
    tokenizer_changed: bool = False
    adapter_merged_into_base: bool = False
    external_transmission_zero: bool = True
    data_117_used_zero: bool = True
    license_verified_true: bool = True


REQUIRED_INVARIANTS = Invariants()


def verify_invariants(state: Invariants = REQUIRED_INVARIANTS) -> None:
    violations: list[str] = []

    if state.base_model_changed:
        violations.append("base_model_changed=True")
    if state.tokenizer_changed:
        violations.append("tokenizer_changed=True")
    if state.adapter_merged_into_base:
        violations.append("adapter_merged_into_base=True")
    if not state.external_transmission_zero:
        violations.append("external_transmission_zero=False")
    if not state.data_117_used_zero:
        violations.append("data_117_used_zero=False")
    if not state.license_verified_true:
        violations.append("license_verified_true=False")

    if violations:
        raise RuntimeError("BLOCK: invariants violated: " + "; ".join(violations))
