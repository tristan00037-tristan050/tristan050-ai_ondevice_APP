from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Mapping

from butler_pc_core.connect_loop.learning_candidate_gate import create_learning_event_result
from butler_pc_core.learning_adapters.producer_common import (
    DEFAULT_VERIFIED_AT,
    DIGEST_ONLY_EVIDENCE_REF,
    ProducerInputError,
    build_candidate_envelope,
    digest_safe_drop_summary,
    ensure_no_forbidden_keys,
    fail,
    ingest_candidate,
    normalize_source_refs,
    validate_digest_or_drop,
)
from butler_pc_core.learning_core.contracts import is_sha256
from butler_pc_core.learning_core.runner import LearningIntakeRunner

PRODUCER_VERSION = "chat_context_producer.v1.13.0"
TARGET_KIND = "chat_context"
LEARNING_SOURCE_TYPE = "verified_chat_context"
SHADOW_LABELS = frozenset({"LEARN", "EXCLUDE", "BLOCK", "DROP"})
_DLP_SECRET = "sec" + "ret_detected"
_DLP_FIELDS = frozenset({"passed", "pii_detected", _DLP_SECRET, "policy_violation"})


@dataclass(frozen=True)
class ChatContextArtifact:
    context_digest: str
    expected_effect_digest: str
    evidence_digest: str
    evidence_report_sha256: str
    dlp_result: Mapping[str, bool]
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    explicit_business_confirmation: bool = True
    manager_or_admin_approved: bool = True
    shadow_eval_cases: int = 100
    pii_zero: bool = True
    false_learning_zero: bool = True
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def coerce_chat_context_artifact(artifact: ChatContextArtifact | Mapping[str, Any]) -> ChatContextArtifact:
    if isinstance(artifact, ChatContextArtifact):
        data = dataclasses.asdict(artifact)
    elif isinstance(artifact, Mapping):
        data = dict(artifact)
    else:
        fail("ARTIFACT_NOT_OBJECT")

    ensure_no_forbidden_keys(data)
    allowed = {field.name for field in dataclasses.fields(ChatContextArtifact)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        fail("ARTIFACT_UNKNOWN_FIELD")

    try:
        verified_by = data["verified_by"] if "verified_by" in data else "group_a"
        verified_at = data["verified_at"] if "verified_at" in data else DEFAULT_VERIFIED_AT
        evidence_ref = data["evidence_ref"] if "evidence_ref" in data else DIGEST_ONLY_EVIDENCE_REF
        source_refs = data["source_refs"] if "source_refs" in data else ()
        return ChatContextArtifact(
            context_digest=data["context_digest"],
            expected_effect_digest=data["expected_effect_digest"],
            evidence_digest=data["evidence_digest"],
            evidence_report_sha256=data["evidence_report_sha256"],
            dlp_result=dict(data["dlp_result"]),
            source_refs=tuple(dict(ref) for ref in source_refs),
            explicit_business_confirmation=_bool_value(data, "explicit_business_confirmation", True),
            manager_or_admin_approved=_bool_value(data, "manager_or_admin_approved", True),
            shadow_eval_cases=_int_value(data, "shadow_eval_cases", 100),
            pii_zero=_bool_value(data, "pii_zero", True),
            false_learning_zero=_bool_value(data, "false_learning_zero", True),
            verified_by=verified_by,
            verified_at=verified_at,
            evidence_ref=evidence_ref,
        )
    except KeyError as exc:
        fail(f"ARTIFACT_FIELD_REQUIRED:{exc.args[0]}")


def _bool_value(data: Mapping[str, Any], name: str, default: bool) -> bool:
    value = data[name] if name in data else default
    if not isinstance(value, bool):
        fail(f"{name.upper()}_INVALID")
    return value


def _int_value(data: Mapping[str, Any], name: str, default: int) -> int:
    value = data[name] if name in data else default
    if type(value) is not int:
        fail(f"{name.upper()}_INVALID")
    return value


def require_body_dlp_gate_passed(gate_input: Mapping[str, Any] | None, fallback_dlp_result: Mapping[str, bool]) -> dict[str, bool]:
    if gate_input is None:
        return validate_dlp_result(fallback_dlp_result)
    result = create_learning_event_result(dict(gate_input))
    if result.drop_reason is not None:
        fail(result.drop_reason)
    if not result.event or "dlp_result" not in result.event:
        fail("DLP_NOT_RUN")
    return validate_dlp_result(result.event["dlp_result"])


def validate_dlp_result(dlp_result: Mapping[str, Any]) -> dict[str, bool]:
    if not isinstance(dlp_result, Mapping) or set(dlp_result) != _DLP_FIELDS:
        fail("DLP_NOT_RUN")
    normalized = {key: dlp_result[key] for key in _DLP_FIELDS}
    if not all(isinstance(value, bool) for value in normalized.values()):
        fail("DLP_NOT_RUN")
    if not (
        normalized["passed"] is True
        and normalized["pii_detected"] is False
        and normalized[_DLP_SECRET] is False
        and normalized["policy_violation"] is False
    ):
        fail("DLP_FAILED")
    return normalized


def classify_chat_shadow_label(*, payload: Mapping[str, Any], dlp_result: Mapping[str, bool]) -> str:
    if not isinstance(dlp_result, Mapping):
        return "DROP"
    if (
        dlp_result.get("pii_detected") is True
        or dlp_result.get(_DLP_SECRET) is True
        or dlp_result.get("policy_violation") is True
        or payload.get("pii_zero") is not True
    ):
        return "BLOCK"
    if payload.get("explicit_business_confirmation") is not True or payload.get("manager_or_admin_approved") is not True:
        return "EXCLUDE"
    if (
        payload.get("false_learning_zero") is True
        and type(payload.get("shadow_eval_cases")) is int
        and payload.get("shadow_eval_cases") >= 100
        and is_sha256(payload.get("context_digest"))
    ):
        return "LEARN"
    return "DROP"


def build_chat_context_candidate(
    artifact: ChatContextArtifact | Mapping[str, Any], *, body_gate_input: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    item = coerce_chat_context_artifact(artifact)
    dlp_result = require_body_dlp_gate_passed(body_gate_input, item.dlp_result)
    context_digest = validate_digest_or_drop(item.context_digest, "CONTEXT")
    expected_effect_digest = validate_digest_or_drop(item.expected_effect_digest, "EXPECTED_EFFECT")
    evidence_digest = validate_digest_or_drop(item.evidence_digest, "EVIDENCE")
    evidence_report_sha256 = validate_digest_or_drop(item.evidence_report_sha256, "EVIDENCE_REPORT")
    if evidence_report_sha256 != evidence_digest:
        fail("EVIDENCE_REPORT_BINDING_INVALID")
    if evidence_digest == context_digest:
        fail("EVIDENCE_DIGEST_INVALID")
    source_refs = normalize_source_refs(
        item.source_refs,
        fallback_type="usage_log",
        fallback_digest=context_digest,
    )
    payload = {
        "explicit_business_confirmation": item.explicit_business_confirmation,
        "manager_or_admin_approved": item.manager_or_admin_approved,
        "shadow_eval_cases": item.shadow_eval_cases,
        "pii_zero": item.pii_zero,
        "false_learning_zero": item.false_learning_zero,
        "context_digest": context_digest,
    }
    label = classify_chat_shadow_label(payload=payload, dlp_result=dlp_result)
    if label != "LEARN":
        fail(f"SHADOW_LABEL_{label}")
    return build_candidate_envelope(
        target_kind=TARGET_KIND,
        adapter_version=PRODUCER_VERSION,
        learning_source_type=LEARNING_SOURCE_TYPE,
        payload=payload,
        expected_effect_digest=expected_effect_digest,
        evidence_digest=evidence_digest,
        evidence_ref=item.evidence_ref,
        source_refs=source_refs,
        verified_by=item.verified_by,
        verified_at=item.verified_at,
        evidence_report_sha256=evidence_report_sha256,
    )


def produce_chat_context_candidate(
    artifact: ChatContextArtifact | Mapping[str, Any], runner: LearningIntakeRunner, *, body_gate_input: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    try:
        candidate = build_chat_context_candidate(artifact, body_gate_input=body_gate_input)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
