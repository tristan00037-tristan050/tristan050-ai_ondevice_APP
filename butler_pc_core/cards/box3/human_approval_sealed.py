from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actual_contracts import stable_json_digest, is_sha256_digest
from .actual_fail_class import (
    APP_MODEL_SCOPE_REQUIRED,
    APPROVAL_CONTEXT_INVALID,
    BLOCK_HUMAN_APPROVAL_EXPIRED,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    BLOCK_HUMAN_APPROVAL_REVOKED,
    BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH,
    EVAL_REQUEST_SCOPE_REQUIRED,
    MODEL_DIGEST_UNAVAILABLE,
    HumanApprovalError,
)

# ── approval context / mode 분리 (v1.2 §3.1) ─────────────────────────────────
APPROVAL_CONTEXT_DESKTOP_APP = "desktop_app"
APPROVAL_CONTEXT_EVAL_PIPELINE = "eval_pipeline"
APPROVAL_MODE_REQUEST = "request_scope"
APPROVAL_MODE_MODEL = "model_scope"


@dataclass(frozen=True)
class HumanApprovalSealedVerdict:
    allowed: bool
    fail_class: str | None
    config_digest: str | None
    approved_by_digest: str | None
    scope_digest: str | None
    approval_mode: str | None = None
    approval_context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_expected_scope_digest(
    config: dict[str, Any] | None,
    *,
    request_digest: str,
    model_digest: str | None,
    context: str,
) -> tuple[str, str]:
    """context 별로 기대 scope digest 와 approval_mode 를 확정한다(v1.2 §3.1).

    - desktop_app: model_scope 만 허용. request_scope fallback 0(APP_MODEL_SCOPE_REQUIRED).
      model_digest 부재는 MODEL_DIGEST_UNAVAILABLE.
    - eval_pipeline: 기존 request_scope 를 유지(그 외 모드는 EVAL_REQUEST_SCOPE_REQUIRED).
    - 그 외 context 는 APPROVAL_CONTEXT_INVALID.
    """
    mode = (config or {}).get("approval_mode", APPROVAL_MODE_REQUEST)

    if context == APPROVAL_CONTEXT_DESKTOP_APP:
        if mode != APPROVAL_MODE_MODEL:
            raise HumanApprovalError(APP_MODEL_SCOPE_REQUIRED)
        if not model_digest:
            raise HumanApprovalError(MODEL_DIGEST_UNAVAILABLE)
        return model_digest, APPROVAL_MODE_MODEL

    if context == APPROVAL_CONTEXT_EVAL_PIPELINE:
        if mode == APPROVAL_MODE_REQUEST:
            return request_digest, APPROVAL_MODE_REQUEST
        raise HumanApprovalError(EVAL_REQUEST_SCOPE_REQUIRED)

    raise HumanApprovalError(APPROVAL_CONTEXT_INVALID)


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def evaluate_human_approval_sealed(
    config: dict[str, Any] | None,
    *,
    expected_scope_digest: str,
    approval_mode: str | None = None,
    approval_context: str | None = None,
) -> HumanApprovalSealedVerdict:
    """승인 판정. approval_mode/approval_context 는 감사 로그용으로 verdict 에 반영한다.

    핵심 판정 로직은 불변(약화 0). 기존 호출부는 그대로 동작한다(두 인자 기본 None).
    """
    verdict = _evaluate_human_approval_core(config, expected_scope_digest=expected_scope_digest)
    if approval_mode is None and approval_context is None:
        return verdict
    return replace(verdict, approval_mode=approval_mode, approval_context=approval_context)


def _evaluate_human_approval_core(config: dict[str, Any] | None, *, expected_scope_digest: str) -> HumanApprovalSealedVerdict:
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
