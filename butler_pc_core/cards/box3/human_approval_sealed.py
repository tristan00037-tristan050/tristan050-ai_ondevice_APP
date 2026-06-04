from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actual_contracts import stable_json_digest, is_sha256_digest
from .actual_fail_class import (
    BLOCK_HUMAN_APPROVAL_EXPIRED,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    BLOCK_HUMAN_APPROVAL_REVOKED,
    BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH,
)


@dataclass(frozen=True)
class HumanApprovalSealedVerdict:
    allowed: bool
    fail_class: str | None
    config_digest: str | None
    approved_by_digest: str | None
    scope_digest: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate_human_approval_sealed(config: dict[str, Any] | None, *, expected_scope_digest: str) -> HumanApprovalSealedVerdict:
    if not isinstance(config, dict):
        return HumanApprovalSealedVerdict(False, "BLOCK_HUMAN_APPROVAL_MISSING", None, None, None)
    digest = stable_json_digest(config)
    if config.get("kill_switch_enabled", True) is True:
        return HumanApprovalSealedVerdict(False, BLOCK_HUMAN_APPROVAL_KILL_SWITCH, digest, config.get("approved_by_digest"), config.get("approval_scope_digest"))
    if config.get("revoked") is True:
        return HumanApprovalSealedVerdict(False, BLOCK_HUMAN_APPROVAL_REVOKED, digest, config.get("approved_by_digest"), config.get("approval_scope_digest"))
    scope = config.get("approval_scope_digest")
    if scope != expected_scope_digest or not is_sha256_digest(scope):
        return HumanApprovalSealedVerdict(False, BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH, digest, config.get("approved_by_digest"), scope)
    expires = _parse_time(config.get("expires_at"))
    if expires is None or expires <= datetime.now(timezone.utc):
        return HumanApprovalSealedVerdict(False, BLOCK_HUMAN_APPROVAL_EXPIRED, digest, config.get("approved_by_digest"), scope)
    if config.get("allow") is not True:
        return HumanApprovalSealedVerdict(False, "BLOCK_HUMAN_APPROVAL_MISSING", digest, config.get("approved_by_digest"), scope)
    approved_by = config.get("approved_by_digest")
    if not is_sha256_digest(approved_by):
        return HumanApprovalSealedVerdict(False, "BLOCK_HUMAN_APPROVAL_MISSING", digest, approved_by, scope)
    return HumanApprovalSealedVerdict(True, None, digest, approved_by, scope)


def load_human_approval_config(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def default_locked_human_approval(scope_digest: str) -> dict[str, Any]:
    return {
        "schema_version": "box3.human_approval.v1",
        "allow": False,
        "kill_switch_enabled": True,
        "revoked": False,
        "approved_by_digest": None,
        "approval_scope_digest": scope_digest,
        "approved_at": None,
        "expires_at": None,
    }
