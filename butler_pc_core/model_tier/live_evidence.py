from __future__ import annotations

from typing import Any, Mapping

from .contracts import is_sha256


LIVE_CASES = frozenset({"box1_simple", "box1_ambiguous", "box3_pass", "box3_review"})


def validate_live_shadow_evidence(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "butler.model_tier_live_shadow_evidence.v1":
        raise ValueError("LIVE_EVIDENCE_SCHEMA_INVALID")
    if payload.get("capture_source") != "butler_app_live_http":
        raise ValueError("LIVE_EVIDENCE_SOURCE_NOT_LIVE_APP")
    if payload.get("synthetic") is not False:
        raise ValueError("LIVE_EVIDENCE_SYNTHETIC_FORBIDDEN")
    if payload.get("chip_family") != "Apple M3 Max":
        raise ValueError("LIVE_EVIDENCE_M3_MAX_REQUIRED")
    if not is_sha256(payload.get("app_executable_digest")):
        raise ValueError("LIVE_EVIDENCE_APP_DIGEST_INVALID")
    cases = payload.get("cases")
    if not isinstance(cases, list) or {row.get("case_id") for row in cases if isinstance(row, dict)} != LIVE_CASES:
        raise ValueError("LIVE_EVIDENCE_CASE_MATRIX_INVALID")
    for row in cases:
        if not isinstance(row, dict):
            raise ValueError("LIVE_EVIDENCE_CASE_INVALID")
        if not is_sha256(row.get("hook_off_response_digest")) or not is_sha256(row.get("hook_on_response_digest")):
            raise ValueError("LIVE_EVIDENCE_RESPONSE_DIGEST_INVALID")
        if row["hook_off_response_digest"] != row["hook_on_response_digest"]:
            raise ValueError("LIVE_EVIDENCE_RESPONSE_CHANGED")
    if payload.get("raw_key_findings") != 0:
        raise ValueError("LIVE_EVIDENCE_RAW_KEY_FINDING")
    counters = payload.get("hook_on_counter_delta")
    if not isinstance(counters, dict):
        raise ValueError("LIVE_EVIDENCE_COUNTERS_REQUIRED")
    if counters.get("submitted", 0) < len(LIVE_CASES) or counters.get("written", 0) < len(LIVE_CASES):
        raise ValueError("LIVE_EVIDENCE_RECORDS_MISSING")
    if counters.get("dropped") != 0 or counters.get("failures") != 0:
        raise ValueError("LIVE_EVIDENCE_RECORDER_LOSS")

