"""Card 1 allowlist validation.

The allowlist is byte-hash pinned like the Card 5 allowlist pattern. Unknown
fields, unknown enum values, and unsafe policy flags fail closed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXPECTED_ALLOWLIST_SHA256 = "cf4cad675cc987178f5da479edf1633de641b1c06aa55479e01041681c0ce972"
ALLOWLIST_PATH = Path(__file__).resolve().parents[4] / "data/card1/card1_allowlist.json"


@dataclass(frozen=True)
class AllowlistDecision:
    ok: bool
    blocked: bool
    fail_class: str | None = None
    violations: tuple[str, ...] = field(default_factory=tuple)


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"BLOCK: Card 1 allowlist not found: {path}")
    actual = compute_sha256(path)
    if actual != EXPECTED_ALLOWLIST_SHA256:
        raise RuntimeError(f"BLOCK: Card 1 allowlist SHA mismatch: expected={EXPECTED_ALLOWLIST_SHA256}, actual={actual}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_card1_output(output: dict[str, Any], allowlist: dict[str, Any] | None = None) -> AllowlistDecision:
    cfg = allowlist or load_allowlist()
    violations: list[str] = []

    allowed_fields = set(cfg["allowed_output_fields"])
    extra_fields = sorted(set(output) - allowed_fields)
    if extra_fields:
        violations.append("unknown_output_fields:" + ",".join(extra_fields))

    if output.get("intent_type") not in cfg["allowed_intent_types"]:
        violations.append("intent_type")
    if output.get("deadline_type") not in cfg["allowed_deadline_types"]:
        violations.append("deadline_type")
    action = output.get("normalized_action")
    if action is not None and action not in cfg["allowed_action_types"]:
        violations.append("normalized_action")

    for flag in output.get("policy_flags", []) or []:
        if flag not in cfg["allowed_policy_flags"]:
            violations.append("policy_flag:" + str(flag))

    if violations:
        return AllowlistDecision(ok=False, blocked=True, fail_class="allowlist_violation", violations=tuple(violations))
    return AllowlistDecision(ok=True, blocked=False)
