from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actual_contracts import is_sha256_digest, stable_json_digest
from .actual_fail_class import (
    BLOCK_HUMAN_APPROVAL_EXPIRED,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    BLOCK_HUMAN_APPROVAL_REVOKED,
    BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH,
)

APPROVAL_MODE_REQUEST = "request_scope"
APPROVAL_MODE_MODEL = "model_scope"
APPROVAL_CONTEXT_EVAL_PIPELINE = "eval_pipeline"
APPROVAL_CONTEXT_DESKTOP_APP = "desktop_app"
APPROVAL_SCOPE_KIND_BOX3_MODEL = "box3_model_scope.v1"
APPROVAL_SCHEMA_V1 = "box3.human_approval.v1"
APPROVAL_SCHEMA_V2 = "box3.human_approval.v2"
APPROVED_MODEL_ROLE_BOX3_DRAFT = "box3_draft"
MODEL_SCOPE_STATUS = "APPROVED_BOX3_MODEL_SCOPE"

_SHA_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
_RFC3339_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MODEL_SCOPE_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "approval_mode",
        "approval_scope_kind",
        "approved_model_role",
        "allow",
        "kill_switch_enabled",
        "revoked",
        "approved_by_digest",
        "device_id_digest",
        "approval_scope_digest",
        "approved_at",
        "expires_at",
        "status",
    }
)


class ApprovalScopeError(RuntimeError):
    """Fail-closed scope resolver error. Message is a reason code only."""


def canonical_sha256_digest(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:") :]
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise ValueError("DIGEST_INVALID")
    return raw


def display_sha256_digest(value: str, *, prefix: bool = True) -> str:
    digest = canonical_sha256_digest(value)
    return f"sha256:{digest}" if prefix else digest


@dataclass(frozen=True)
class HumanApprovalSealedVerdict:
    allowed: bool
    fail_class: str | None
    config_digest: str | None
    approved_by_digest: str | None
    scope_digest: str | None
    mode: str = APPROVAL_MODE_REQUEST
    approval_scope_kind: str | None = None
    model_digest_status: str = "not_applicable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def blocked(
        cls,
        *,
        fail_class: str,
        config_digest: str | None = None,
        approved_by_digest: str | None = None,
        scope_digest: str | None = None,
        mode: str = APPROVAL_MODE_REQUEST,
        approval_scope_kind: str | None = None,
        model_digest_status: str = "blocked",
    ) -> "HumanApprovalSealedVerdict":
        return cls(False, fail_class, config_digest, approved_by_digest, scope_digest, mode, approval_scope_kind, model_digest_status)


def _parse_time(value: str | None):
    if not value or not isinstance(value, str):
        return None
    if not _RFC3339_Z_RE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _validate_model_scope_schema(config: dict[str, Any]) -> None:
    unknown = set(config) - MODEL_SCOPE_REQUIRED_KEYS
    if unknown:
        raise ApprovalScopeError("APPROVAL_SCHEMA_INVALID")
    missing = MODEL_SCOPE_REQUIRED_KEYS - set(config)
    if "device_id_digest" in missing:
        raise ApprovalScopeError("APPROVAL_DEVICE_MISSING")
    if missing:
        raise ApprovalScopeError("APPROVAL_SCHEMA_INVALID")
    if config.get("schema_version") != APPROVAL_SCHEMA_V2:
        raise ApprovalScopeError("APPROVAL_SCHEMA_INVALID")
    if config.get("approval_mode") != APPROVAL_MODE_MODEL:
        raise ApprovalScopeError("APPROVAL_MODE_REQUIRED")
    if config.get("approval_scope_kind") != APPROVAL_SCOPE_KIND_BOX3_MODEL:
        raise ApprovalScopeError("APPROVAL_SCOPE_KIND_INVALID")
    if config.get("approved_model_role") != APPROVED_MODEL_ROLE_BOX3_DRAFT:
        raise ApprovalScopeError("APPROVED_MODEL_ROLE_INVALID")
    if config.get("status") != MODEL_SCOPE_STATUS:
        raise ApprovalScopeError("APPROVAL_STATUS_INVALID")
    for key in ("approved_by_digest", "device_id_digest", "approval_scope_digest"):
        if not isinstance(config.get(key), str) or not _SHA_RE.fullmatch(config[key]):
            raise ApprovalScopeError(f"{key.upper()}_INVALID")
    if _parse_time(config.get("approved_at")) is None:
        raise ApprovalScopeError("APPROVED_AT_INVALID")
    if _parse_time(config.get("expires_at")) is None:
        raise ApprovalScopeError("EXPIRES_AT_INVALID")
    if config.get("allow") is not True:
        raise ApprovalScopeError("APPROVAL_ALLOW_INVALID")
    if config.get("kill_switch_enabled") is not False:
        raise ApprovalScopeError(BLOCK_HUMAN_APPROVAL_KILL_SWITCH)
    if config.get("revoked") is not False:
        raise ApprovalScopeError(BLOCK_HUMAN_APPROVAL_REVOKED)


def resolve_expected_scope_digest(
    config: dict[str, Any] | None,
    *,
    request_digest: str,
    model_digest: str | None,
    context: str,
    runtime_device_digest: str | None = None,
) -> tuple[str, str]:
    cfg = config or {}
    mode = cfg.get("approval_mode", APPROVAL_MODE_REQUEST)
    if context == APPROVAL_CONTEXT_EVAL_PIPELINE:
        if mode in (None, "", APPROVAL_MODE_REQUEST):
            return display_sha256_digest(request_digest, prefix=True), APPROVAL_MODE_REQUEST
        raise ApprovalScopeError("APPROVAL_MODE_INVALID")
    if context == APPROVAL_CONTEXT_DESKTOP_APP:
        if mode != APPROVAL_MODE_MODEL:
            raise ApprovalScopeError("APPROVAL_MODE_REQUIRED")
        _validate_model_scope_schema(cfg)
        if not model_digest:
            raise ApprovalScopeError("MODEL_DIGEST_UNAVAILABLE")
        if not runtime_device_digest:
            raise ApprovalScopeError("DEVICE_DIGEST_UNAVAILABLE")
        stored_device = cfg.get("device_id_digest")
        if not stored_device:
            raise ApprovalScopeError("APPROVAL_DEVICE_MISSING")
        try:
            if canonical_sha256_digest(stored_device) != canonical_sha256_digest(runtime_device_digest):
                raise ApprovalScopeError("APPROVAL_DEVICE_MISMATCH")
        except ValueError as exc:
            raise ApprovalScopeError("APPROVAL_DEVICE_MISMATCH") from exc
        return display_sha256_digest(model_digest, prefix=True), APPROVAL_MODE_MODEL
    raise ApprovalScopeError("APPROVAL_CONTEXT_INVALID")


def evaluate_human_approval_sealed(
    config: dict[str, Any] | None,
    *,
    expected_scope_digest: str,
    mode: str = APPROVAL_MODE_REQUEST,
) -> HumanApprovalSealedVerdict:
    if not isinstance(config, dict):
        return HumanApprovalSealedVerdict.blocked(fail_class="BLOCK_HUMAN_APPROVAL_MISSING", mode=mode)
    digest = stable_json_digest(config)
    approval_scope_kind = config.get("approval_scope_kind") if isinstance(config.get("approval_scope_kind"), str) else None
    if config.get("kill_switch_enabled", True) is True:
        return HumanApprovalSealedVerdict.blocked(
            fail_class=BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
            config_digest=digest,
            approved_by_digest=config.get("approved_by_digest"),
            scope_digest=config.get("approval_scope_digest"),
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    if config.get("revoked") is True:
        return HumanApprovalSealedVerdict.blocked(
            fail_class=BLOCK_HUMAN_APPROVAL_REVOKED,
            config_digest=digest,
            approved_by_digest=config.get("approved_by_digest"),
            scope_digest=config.get("approval_scope_digest"),
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    scope = config.get("approval_scope_digest")
    try:
        scope_matches = canonical_sha256_digest(scope) == canonical_sha256_digest(expected_scope_digest)
    except Exception:
        scope_matches = False
    if not scope_matches:
        return HumanApprovalSealedVerdict.blocked(
            fail_class=BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH,
            config_digest=digest,
            approved_by_digest=config.get("approved_by_digest"),
            scope_digest=scope,
            mode=mode,
            approval_scope_kind=approval_scope_kind,
            model_digest_status="mismatch" if mode == APPROVAL_MODE_MODEL else "not_applicable",
        )
    expires = _parse_time(config.get("expires_at"))
    if expires is None or expires <= datetime.now(timezone.utc):
        return HumanApprovalSealedVerdict.blocked(
            fail_class=BLOCK_HUMAN_APPROVAL_EXPIRED,
            config_digest=digest,
            approved_by_digest=config.get("approved_by_digest"),
            scope_digest=scope,
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    if config.get("allow") is not True:
        return HumanApprovalSealedVerdict.blocked(
            fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
            config_digest=digest,
            approved_by_digest=config.get("approved_by_digest"),
            scope_digest=scope,
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    approved_by = config.get("approved_by_digest")
    try:
        approved_by_display = display_sha256_digest(str(approved_by or ""), prefix=True)
    except ValueError:
        return HumanApprovalSealedVerdict.blocked(
            fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
            config_digest=digest,
            approved_by_digest=approved_by,
            scope_digest=scope,
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    if not is_sha256_digest(approved_by_display):
        return HumanApprovalSealedVerdict.blocked(
            fail_class="BLOCK_HUMAN_APPROVAL_MISSING",
            config_digest=digest,
            approved_by_digest=approved_by,
            scope_digest=scope,
            mode=mode,
            approval_scope_kind=approval_scope_kind,
        )
    return HumanApprovalSealedVerdict(
        True,
        None,
        digest,
        approved_by_display,
        display_sha256_digest(scope, prefix=True),
        mode,
        approval_scope_kind,
        "matched" if mode == APPROVAL_MODE_MODEL else "not_applicable",
    )


def load_human_approval_config(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def default_locked_human_approval(scope_digest: str) -> dict[str, Any]:
    return {
        "schema_version": APPROVAL_SCHEMA_V1,
        "approval_mode": APPROVAL_MODE_REQUEST,
        "allow": False,
        "kill_switch_enabled": True,
        "revoked": False,
        "approved_by_digest": None,
        "approval_scope_digest": display_sha256_digest(scope_digest, prefix=True) if scope_digest else None,
        "approved_at": None,
        "expires_at": None,
    }
