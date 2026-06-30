"""Verified rule-base learning flow for Box5 accounting guards.

This package intentionally stays separate from connect_loop learning_event.v1.
It queues digest-only deterministic rule patch candidates for human review and
never applies, commits, pushes, trains, or hot-patches runtime behavior.
"""

from .candidate_gate import (
    GateDecision,
    explain_drop_reason,
    gate_candidate,
    is_verified_rule_base_candidate,
)
from .contracts import (
    VerifiedRuleBaseCandidate,
    VerifiedRuleBaseContractError,
    make_candidate,
    sha256_text,
    validate_candidate_dict,
)

__all__ = [
    "GateDecision",
    "VerifiedRuleBaseCandidate",
    "VerifiedRuleBaseContractError",
    "explain_drop_reason",
    "gate_candidate",
    "is_verified_rule_base_candidate",
    "make_candidate",
    "sha256_text",
    "validate_candidate_dict",
]
