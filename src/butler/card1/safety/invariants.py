"""Card 1 six invariants.

The invariants adapt the Card 5 fail-closed pattern to request core parsing.
Every violation blocks the output before downstream use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


INVARIANT_NAMES = (
    "output_is_object",
    "intent_present",
    "deadline_requires_digest",
    "auto_apply_guarded",
    "content_not_retained_flag",
    "no_external_egress_flag",
)


@dataclass(frozen=True)
class InvariantReport:
    ok: bool
    blocked: bool
    violations: tuple[str, ...] = field(default_factory=tuple)


def validate_six_invariants(output: dict[str, Any]) -> InvariantReport:
    violations: list[str] = []

    if not isinstance(output, dict):
        return InvariantReport(ok=False, blocked=True, violations=("output_is_object",))

    if not output.get("intent_type"):
        violations.append("intent_present")

    deadline_type = output.get("deadline_type")
    if deadline_type and deadline_type != "NONE" and not output.get("source_digest16"):
        violations.append("deadline_requires_digest")

    auto_apply = bool(output.get("auto_apply_allowed", False))
    confidence = float(output.get("confidence", 0.0) or 0.0)
    if auto_apply and confidence < 0.95:
        violations.append("auto_apply_guarded")

    flags = set(output.get("policy_flags", []) or [])
    if "content_not_retained" not in flags:
        violations.append("content_not_retained_flag")
    if "no_external_egress" not in flags:
        violations.append("no_external_egress_flag")

    if violations:
        return InvariantReport(ok=False, blocked=True, violations=tuple(violations))
    return InvariantReport(ok=True, blocked=False)
