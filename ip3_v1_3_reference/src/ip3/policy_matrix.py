from __future__ import annotations

from typing import Dict, Iterable, Mapping

POLICY_LABELS = ("Restricted", "Confidential", "Internal", "Public")
ROUTING_TARGETS = ("local_1_7b", "local_4b", "central_server", "external_api", "blocked")

# Device x policy routing defaults; model executable checks happen after this precheck.
POLICY_MATRIX: Dict[str, Dict[str, tuple[str, ...]]] = {
    "Restricted": {"A": ("local_1_7b",), "B": ("local_1_7b",), "C": ("blocked",), "D": ("blocked",)},
    "Confidential": {"A": ("local_1_7b", "central_server"), "B": ("local_1_7b", "central_server"), "C": ("central_server",), "D": ("blocked",)},
    "Internal": {"A": ("local_1_7b", "central_server"), "B": ("central_server", "local_1_7b"), "C": ("central_server",), "D": ("central_server",)},
    "Public": {"A": ("local_1_7b", "central_server", "external_api"), "B": ("central_server", "external_api", "local_1_7b"), "C": ("central_server", "external_api"), "D": ("external_api", "central_server")},
}

def allowed_targets(data_sensitivity: str, device_class: str, *, external_api_enabled: bool = False) -> tuple[str, ...]:
    if data_sensitivity not in POLICY_LABELS:
        return ("blocked",)
    candidates = POLICY_MATRIX[data_sensitivity].get(device_class, ("blocked",))
    if not external_api_enabled:
        candidates = tuple(x for x in candidates if x != "external_api")
    return candidates or ("blocked",)


def pep_decision_allows(policy_decision: Mapping[str, object]) -> bool:
    return bool(policy_decision.get("allow")) and policy_decision.get("decision") not in {"deny", "block", "blocked"}
