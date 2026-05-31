"""PR-E Learning Candidate Gate.

This module creates learning_event.v1 candidates from digest-only usage logs
only when approved sanitized references, policy gates, DLP booleans, and schema
validation all pass. It never trains models and never treats usage_log itself as
learning data.
"""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from jsonschema.exceptions import ValidationError

from .dlp_guard import assert_no_raw_or_secret_material, scan_runtime_text
from .learning_event_schema import validate_learning_event, validate_usage_log

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
APPROVED_REF_RE = re.compile(r"^(vault|keyring)://[^\s]{1,240}$")

INTENT_TO_LEARNING_TYPE = {
    "memory_search": "memory_search",
    "form_convert": "form_convert",
    "draft_write": "draft_write",
    "accounting_classify": "accounting_classify",
    "general_chat": "intent_routing",
    "unknown": "intent_routing",
}


@dataclass(frozen=True)
class CandidateRef:
    source_usage_log_id: str
    usage_log: dict[str, Any]
    label: dict[str, str]


@dataclass(frozen=True)
class ApprovedRefBundle:
    approved_text_ref: str
    approved_text_digest: str
    sanitized_summary_digest: str
    runtime_text_for_dlp: str | None = None


@dataclass(frozen=True)
class GateResult:
    event: dict[str, Any] | None
    drop_reason: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_rfc3339(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _quality_for(usage_log: dict[str, Any]) -> str:
    confidence = float(usage_log.get("routing_confidence", 0.0))
    if confidence >= 0.85:
        return "good"
    if confidence >= 0.65:
        return "fair"
    return "poor"


def _is_candidate_usage_log(usage_log: dict[str, Any]) -> bool:
    try:
        validate_usage_log(usage_log)
    except ValidationError:
        return False
    return (
        usage_log.get("learning_candidate") is True
        and usage_log.get("policy_decision") == "allow"
        and usage_log.get("integration_mode") == "real"
        and usage_log.get("real_validation_done") is True
        and usage_log.get("external_send_zero") is True
        and usage_log.get("raw_text_logged") is False
        and usage_log.get("retention_class") == "audit_digest_only"
    )


def select_learning_candidates(usage_logs: list[dict[str, Any]]) -> list[CandidateRef]:
    candidates: list[CandidateRef] = []
    for usage_log in usage_logs:
        if not _is_candidate_usage_log(usage_log):
            continue
        copied = copy.deepcopy(usage_log)
        candidates.append(
            CandidateRef(
                source_usage_log_id=str(copied["log_id"]),
                usage_log=copied,
                label={
                    "intent_label": str(copied["intent_label"]),
                    "target_box_id": str(copied["box_id"]),
                    "quality": _quality_for(copied),
                },
            )
        )
    return candidates


def build_learning_gate_input(
    candidate: CandidateRef,
    approved_ref_bundle: ApprovedRefBundle | None,
    policy_task_envelope: dict[str, Any],
    *,
    policy_approval: dict[str, str] | None = None,
    dlp_result: dict[str, bool] | None = None,
) -> dict[str, Any]:
    resolved_dlp = dlp_result
    if resolved_dlp is None and approved_ref_bundle and approved_ref_bundle.runtime_text_for_dlp is not None:
        resolved_dlp = scan_runtime_text(approved_ref_bundle.runtime_text_for_dlp)
    return {
        "source_usage_log": copy.deepcopy(candidate.usage_log),
        "policy_task_envelope": copy.deepcopy(policy_task_envelope),
        "approved_text_ref": approved_ref_bundle.approved_text_ref if approved_ref_bundle else None,
        "approved_text_digest": approved_ref_bundle.approved_text_digest if approved_ref_bundle else None,
        "sanitized_summary_digest": approved_ref_bundle.sanitized_summary_digest if approved_ref_bundle else None,
        "label": copy.deepcopy(candidate.label),
        "policy_approval": copy.deepcopy(policy_approval)
        if policy_approval is not None
        else {
            "decision": "needs_review",
            "approver_role": "manager",
            "reason_code": "LEARNING_CANDIDATE_CREATED",
        },
        "dlp_result": copy.deepcopy(resolved_dlp),
    }


def _drop_reason(gate_input: dict[str, Any], now: datetime) -> str | None:
    source_usage_log = gate_input.get("source_usage_log")
    if not isinstance(source_usage_log, dict) or not _is_candidate_usage_log(source_usage_log):
        return "SOURCE_USAGE_LOG_NOT_ELIGIBLE"

    # Codex P1 정정 (2026-05-31): caller가 gate_input["label"]을 schema-consistent하지만
    # source usage_log와 다른 값으로 주입/변형(예: memory_search 출처 로그 + form_convert
    # 라벨)하면 learning_event 스키마는 label 내부 일관성만 보므로 통과한다. 그러면
    # source_usage_log_id가 가리키는 audited log와 학습된 task가 어긋나 wrong task로
    # 학습되고 audit 추적이 깨진다. 게이트 단계에서 label.intent_label/target_box_id가
    # source_usage_log.intent_label/box_id와 정확히 일치하는지 강제한다.
    label = gate_input.get("label")
    if not isinstance(label, dict):
        return "LABEL_MISSING"
    if (
        label.get("intent_label") != source_usage_log.get("intent_label")
        or label.get("target_box_id") != source_usage_log.get("box_id")
    ):
        return "LABEL_SOURCE_DRIFT"

    envelope = gate_input.get("policy_task_envelope")
    if not isinstance(envelope, dict):
        return "POLICY_ENVELOPE_MISSING"
    if envelope.get("learning_allowed") is not True:
        return "LEARNING_NOT_ALLOWED"

    approved_text_ref = gate_input.get("approved_text_ref")
    if not isinstance(approved_text_ref, str) or not approved_text_ref:
        return "APPROVED_TEXT_REF_MISSING"
    if not APPROVED_REF_RE.fullmatch(approved_text_ref):
        return "APPROVED_TEXT_REF_FORBIDDEN"

    if not isinstance(gate_input.get("approved_text_digest"), str) or not SHA256_RE.fullmatch(gate_input["approved_text_digest"]):
        return "APPROVED_TEXT_DIGEST_MISSING"
    if not isinstance(gate_input.get("sanitized_summary_digest"), str) or not SHA256_RE.fullmatch(gate_input["sanitized_summary_digest"]):
        return "SANITIZED_SUMMARY_DIGEST_MISSING"

    dlp_result = gate_input.get("dlp_result")
    if not isinstance(dlp_result, dict):
        return "DLP_NOT_RUN"
    if not (
        dlp_result.get("passed") is True
        and dlp_result.get("pii_detected") is False
        and dlp_result.get("secret_detected") is False
        and dlp_result.get("policy_violation") is False
    ):
        return "DLP_FAILED"

    retention_days = envelope.get("retention_days")
    if not isinstance(retention_days, int) or retention_days < 1:
        return "RETENTION_INVALID"
    expires_at = envelope.get("expires_at")
    if not isinstance(expires_at, str):
        return "EXPIRES_AT_MISSING"
    parsed_expires = _parse_rfc3339(expires_at)
    if parsed_expires is None:
        return "EXPIRES_AT_INVALID"
    if parsed_expires <= now:
        return "RETENTION_EXPIRED"

    try:
        assert_no_raw_or_secret_material(gate_input)
    except ValueError:
        return "RAW_OR_SECRET_MATERIAL_FORBIDDEN"
    return None


def create_learning_event_result(
    gate_input: dict[str, Any],
    *,
    now: datetime | None = None,
) -> GateResult:
    current_time = now or _utc_now()
    drop = _drop_reason(gate_input, current_time)
    if drop is not None:
        return GateResult(event=None, drop_reason=drop)

    source_usage_log = gate_input["source_usage_log"]
    envelope = gate_input["policy_task_envelope"]
    event = {
        "learning_event_id": "lev-" + uuid.uuid4().hex,
        "source_usage_log_id": source_usage_log["log_id"],
        "created_at": _format_rfc3339(current_time),
        "status": "CANDIDATE",
        "tenant_scope": envelope["tenant_scope"],
        "learning_type": INTENT_TO_LEARNING_TYPE[str(gate_input["label"]["intent_label"])],
        "raw_input_saved": False,
        "raw_output_saved": False,
        "approved_text_ref": gate_input["approved_text_ref"],
        "approved_text_digest": gate_input["approved_text_digest"],
        "sanitized_summary_digest": gate_input["sanitized_summary_digest"],
        "sanitized_summary_saved": False,
        "label": copy.deepcopy(gate_input["label"]),
        "policy_approval": copy.deepcopy(gate_input["policy_approval"]),
        "dlp_result": copy.deepcopy(gate_input["dlp_result"]),
        "retention_days": envelope["retention_days"],
        "expires_at": envelope["expires_at"],
        "verified_for_training": False,
        "schema_version": "learning_event.v1",
    }
    try:
        assert_no_raw_or_secret_material(event)
        validate_learning_event(event)
    except (ValueError, ValidationError):
        return GateResult(event=None, drop_reason="SCHEMA_VALIDATION_FAILED")
    return GateResult(event=event, drop_reason=None)


def create_learning_event(gate_input: dict[str, Any]) -> dict[str, Any] | None:
    return create_learning_event_result(gate_input).event


def _approval_dlp_passes(event: dict[str, Any]) -> bool:
    dlp = event.get("dlp_result", {})
    return (
        dlp.get("passed") is True
        and dlp.get("pii_detected") is False
        and dlp.get("secret_detected") is False
        and dlp.get("policy_violation") is False
    )


def approve_learning_event(
    event: dict[str, Any],
    approval: dict[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    current_time = now or _utc_now()
    expires = _parse_rfc3339(str(event.get("expires_at", "")))
    if event.get("status") != "CANDIDATE":
        return None
    if approval.get("decision") != "approved":
        return None
    if not _approval_dlp_passes(event):
        return None
    if expires is None or expires <= current_time:
        return expire_learning_event(event, now=current_time)

    approved = copy.deepcopy(event)
    approved["status"] = "APPROVED"
    approved["policy_approval"] = copy.deepcopy(approval)
    approved["verified_for_training"] = True
    try:
        assert_no_raw_or_secret_material(approved)
        validate_learning_event(approved)
    except (ValueError, ValidationError):
        return None
    return approved


def reject_learning_event(event: dict[str, Any], reason_code: str = "LEARNING_REJECTED") -> dict[str, Any]:
    rejected = copy.deepcopy(event)
    rejected["status"] = "REJECTED"
    rejected["verified_for_training"] = False
    rejected["policy_approval"] = {
        "decision": "rejected",
        "approver_role": "manager",
        "reason_code": reason_code,
    }
    validate_learning_event(rejected)
    return rejected


def expire_learning_event(event: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    expired = copy.deepcopy(event)
    expired["status"] = "EXPIRED"
    expired["verified_for_training"] = False
    expired["policy_approval"] = {
        "decision": "rejected",
        "approver_role": "system",
        "reason_code": "RETENTION_EXPIRED",
    }
    validate_learning_event(expired)
    return expired
