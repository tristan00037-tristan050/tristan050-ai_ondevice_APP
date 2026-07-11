from __future__ import annotations

import math
from typing import Any, Mapping

from .contracts import TaskProfile, is_sha256, stable_digest, validate_reason_code


FORBIDDEN_TASK_KEYS = frozenset(
    {
        "text",
        "query",
        "prompt",
        "reference_text",
        "draft_text",
        "draft",
        "file_path",
        "path",
        "raw",
        "payload",
        "content",
    }
)
ALLOWED_FACT_KEYS = frozenset(
    {
        "payload_digest",
        "input_chars",
        "attachment_count",
        "total_attachment_bytes",
        "requested_output_tokens",
        "reference_count",
        "structured_output_required",
        "deterministic_path_available",
        "ambiguous_signals",
        "competing_intents",
        "ambiguity_score",
        "quality_risk_flags",
        "security_risk_flags",
    }
)


def _checked_int(facts: Mapping[str, Any], key: str, *, maximum: int) -> int:
    value = facts.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError("TASK_PROFILE_COUNT_INVALID")
    return value


def _bounded_ratio(value: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, value / denominator))


def _reason_flags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError("TASK_PROFILE_RISK_FLAGS_INVALID")
    flags = tuple(sorted(set(value)))
    if not all(isinstance(flag, str) for flag in flags):
        raise ValueError("TASK_PROFILE_RISK_FLAGS_INVALID")
    for flag in flags:
        validate_reason_code(flag)
    return flags


def classify_task_complexity(box_id: str, facts: Mapping[str, Any]) -> TaskProfile:
    """Build a task profile from counts, booleans, reason codes, and digests only."""
    keys = set(facts)
    if keys & FORBIDDEN_TASK_KEYS:
        raise ValueError("RAW_FIELD_FORBIDDEN_IN_TASK_PROFILE")
    if keys - ALLOWED_FACT_KEYS:
        raise ValueError("TASK_PROFILE_UNKNOWN_FIELD")
    if box_id not in {"1", "3"}:
        raise ValueError("TASK_PROFILE_BOX_UNSUPPORTED")

    input_chars = _checked_int(facts, "input_chars", maximum=100_000_000)
    attachment_count = _checked_int(facts, "attachment_count", maximum=1_000)
    total_bytes = _checked_int(facts, "total_attachment_bytes", maximum=1 << 50)
    requested_output = _checked_int(facts, "requested_output_tokens", maximum=1_000_000)
    reference_count = _checked_int(facts, "reference_count", maximum=10_000)
    ambiguous_signals = _checked_int(facts, "ambiguous_signals", maximum=10_000)
    competing_intents = _checked_int(facts, "competing_intents", maximum=10_000)
    structured = facts.get("structured_output_required", False)
    deterministic = facts.get("deterministic_path_available", False)
    if not isinstance(structured, bool) or not isinstance(deterministic, bool):
        raise ValueError("TASK_PROFILE_BOOLEAN_INVALID")

    provided_ambiguity = facts.get("ambiguity_score")
    if provided_ambiguity is not None:
        if (
            isinstance(provided_ambiguity, bool)
            or not isinstance(provided_ambiguity, (int, float))
            or not 0.0 <= float(provided_ambiguity) <= 1.0
        ):
            raise ValueError("TASK_PROFILE_AMBIGUITY_INVALID")
        ambiguity = float(provided_ambiguity)
    else:
        ambiguity = min(
            1.0,
            0.35 * _bounded_ratio(ambiguous_signals, 3)
            + 0.35 * _bounded_ratio(competing_intents, 2)
            + 0.15 * _bounded_ratio(reference_count, 4)
            + 0.15 * _bounded_ratio(input_chars, 12_000),
        )

    payload_digest = facts.get("payload_digest")
    digest_source = {
        "box_id": box_id,
        "input_chars": input_chars,
        "attachment_count": attachment_count,
        "total_attachment_bytes": total_bytes,
        "requested_output_tokens": requested_output,
        "reference_count": reference_count,
        "structured_output_required": structured,
        "deterministic_path_available": deterministic,
        "ambiguous_signals": ambiguous_signals,
        "competing_intents": competing_intents,
        "ambiguity_score": round(ambiguity, 4),
    }
    if payload_digest is None:
        payload_digest = stable_digest(digest_source)
    if not is_sha256(payload_digest):
        raise ValueError("TASK_PROFILE_DIGEST_INVALID")

    profile = TaskProfile(
        schema_version="butler.task_profile.v1",
        box_id=box_id,
        task_class=("box1_request_routing" if box_id == "1" else "box3_grounded_draft"),
        payload_digest=payload_digest,
        input_chars=input_chars,
        attachment_count=attachment_count,
        total_attachment_bytes=total_bytes,
        estimated_input_tokens=max(1, math.ceil(input_chars / 3.2)) if input_chars else 0,
        requested_output_tokens=requested_output,
        reference_count=reference_count,
        structured_output_required=structured,
        deterministic_path_available=deterministic,
        ambiguity_score=round(ambiguity, 4),
        quality_risk_flags=_reason_flags(facts.get("quality_risk_flags")),
        security_risk_flags=_reason_flags(facts.get("security_risk_flags")),
    )
    profile.validate()
    return profile
