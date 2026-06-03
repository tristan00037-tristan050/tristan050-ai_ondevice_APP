from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .real_contracts import is_sha256_digest, stable_json_digest
from .real_fail_class import (
    BLOCK_HUMAN_APPROVAL_EXPIRED,
    BLOCK_HUMAN_APPROVAL_INVALID,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    BLOCK_HUMAN_APPROVAL_MISSING,
    BLOCK_HUMAN_APPROVAL_REVOKED,
    BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH,
)


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TIME_VALUE_INVALID")
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


@dataclass(frozen=True)
class HumanApprovalConfig:
    schema_version: str = "box3.human_approval.v1"
    allow: bool = False
    approved_by_digest: Optional[str] = None
    approval_scope_digest: Optional[str] = None
    approved_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked: bool = False
    kill_switch_enabled: bool = True
    evidence_digest: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def config_digest(self) -> str:
        return stable_json_digest(self.to_dict())


@dataclass(frozen=True)
class HumanApprovalVerdict:
    allowed: bool
    fail_class: Optional[str]
    config_digest: Optional[str]
    approval_scope_digest: Optional[str]
    kill_switch_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_human_approval_config(path: Path | str | None) -> HumanApprovalConfig:
    if path is None:
        return HumanApprovalConfig()
    p = Path(path)
    if not p.exists():
        return HumanApprovalConfig()
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(BLOCK_HUMAN_APPROVAL_INVALID)
    return HumanApprovalConfig(
        schema_version=data.get("schema_version", "box3.human_approval.v1"),
        allow=bool(data.get("allow", False)),
        approved_by_digest=data.get("approved_by_digest"),
        approval_scope_digest=data.get("approval_scope_digest"),
        approved_at=data.get("approved_at"),
        expires_at=data.get("expires_at"),
        revoked=bool(data.get("revoked", False)),
        kill_switch_enabled=bool(data.get("kill_switch_enabled", True)),
        evidence_digest=data.get("evidence_digest"),
    )


def evaluate_human_approval(
    config: HumanApprovalConfig | None,
    *,
    expected_scope_digest: str | None = None,
    now: datetime | None = None,
) -> HumanApprovalVerdict:
    cfg = config or HumanApprovalConfig()
    if cfg.schema_version != "box3.human_approval.v1":
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_INVALID, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if cfg.kill_switch_enabled:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_KILL_SWITCH, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if cfg.revoked:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_REVOKED, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if not cfg.allow:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_MISSING, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if not (is_sha256_digest(cfg.approved_by_digest) and is_sha256_digest(cfg.approval_scope_digest)):
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_INVALID, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if expected_scope_digest and cfg.approval_scope_digest != expected_scope_digest:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if not cfg.approved_at or not cfg.expires_at:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_INVALID, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    current = now or datetime.now(timezone.utc)
    try:
        expires = _parse_time(cfg.expires_at)
    except Exception:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_INVALID, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if current > expires:
        return HumanApprovalVerdict(False, BLOCK_HUMAN_APPROVAL_EXPIRED, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
    return HumanApprovalVerdict(True, None, cfg.config_digest, cfg.approval_scope_digest, cfg.kill_switch_enabled)
