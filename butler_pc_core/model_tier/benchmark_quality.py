from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityVerdict:
    passed: bool
    schema_pass: bool
    dlp_pass: bool
    grounding_pass: bool
    escalation_recommended: bool
    metrics: dict[str, Any]
    failure_code: str | None = None


def evaluate_box1(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    dlp_pass: bool = True,
) -> QualityVerdict:
    required = {"intent_label", "target_box_id", "fallback_required", "reason_code", "policy_precheck"}
    schema_pass = isinstance(actual, dict) and required <= set(actual)
    intent_ok = schema_pass and actual.get("intent_label") == expected.get("intent_label")
    box_ok = schema_pass and actual.get("target_box_id") == expected.get("target_box_id")
    fallback_ok = schema_pass and actual.get("fallback_required") is expected.get("fallback_required")
    allowed_reasons = expected.get("allowed_reason_codes", [])
    reason_ok = schema_pass and (
        not allowed_reasons or actual.get("reason_code") in allowed_reasons
    )
    policy_outcome = expected.get("policy_outcome")
    policy_ok = True if policy_outcome is None else actual.get("policy_precheck") == policy_outcome
    unsafe_direct = bool(
        expected.get("fallback_required") and actual.get("fallback_required") is False
    )
    passed = bool(
        schema_pass
        and dlp_pass
        and intent_ok
        and box_ok
        and fallback_ok
        and reason_ok
        and policy_ok
        and not unsafe_direct
    )
    return QualityVerdict(
        passed=passed,
        schema_pass=schema_pass,
        dlp_pass=dlp_pass,
        grounding_pass=True,
        escalation_recommended=not passed,
        metrics={
            "intent_exact_match": bool(intent_ok),
            "target_box_exact_match": bool(box_ok),
            "fallback_required_exact_match": bool(fallback_ok),
            "reason_code_allowed": bool(reason_ok),
            "policy_outcome_match": bool(policy_ok),
            "unsafe_direct_dispatch_count": int(unsafe_direct),
        },
        failure_code=None if passed else "BOX1_QUALITY_GATE_FAILED",
    )


def evaluate_box3(
    expected: dict[str, Any],
    output_text: str,
    *,
    dlp_pass: bool = True,
) -> QualityVerdict:
    text = str(output_text or "")
    required_anchors = [str(item) for item in expected.get("required_anchors", [])]
    forbidden_values = [
        str(item) for item in expected.get("forbidden_invented_values", [])
    ]
    labels = ("제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안")
    anchor_hits = sum(anchor in text for anchor in required_anchors)
    anchor_coverage = anchor_hits / len(required_anchors) if required_anchors else 1.0
    forbidden_hits = sum(value in text for value in forbidden_values)
    schema_pass = all(label in text for label in labels)
    skeleton_echo = any(
        marker in text
        for marker in ("<근거_", "FORMAT_HINT:", "REFERENCES:", "[REF ", "[EVIDENCE ")
    )
    grounding_pass = bool(
        anchor_coverage >= float(expected.get("minimum_anchor_coverage", 0.8))
        and forbidden_hits == 0
    )
    content_drift_pass = bool(anchor_hits > 0) if required_anchors else True
    passed = bool(
        schema_pass
        and dlp_pass
        and grounding_pass
        and content_drift_pass
        and not skeleton_echo
    )
    expected_gate = expected.get("expected_gate_class", "PASS")
    if expected_gate == "HARD_FAIL":
        # A hard-fail fixture is successful only when the runtime explicitly blocks it;
        # a free-form generated draft can never satisfy that contract.
        passed = False
    escalation = bool(
        not passed
        and expected.get("repair_eligible", True) is True
        and expected_gate != "HARD_FAIL"
    )
    return QualityVerdict(
        passed=passed,
        schema_pass=schema_pass,
        dlp_pass=dlp_pass,
        grounding_pass=grounding_pass,
        escalation_recommended=escalation,
        metrics={
            "content_drift_pass": content_drift_pass,
            "skeleton_meta_echo_pass": not skeleton_echo,
            "required_anchor_coverage": round(anchor_coverage, 6),
            "required_anchor_hit_count": anchor_hits,
            "forbidden_invented_value_count": forbidden_hits,
            "unsupported_count": forbidden_hits,
            "no_evidence_count": max(0, len(required_anchors) - anchor_hits),
            "repair_success": bool(passed and expected.get("repair_fixture") is True),
        },
        failure_code=(
            None
            if passed
            else (
                "BOX3_HARD_GATE_EXPECTED"
                if expected_gate == "HARD_FAIL"
                else "BOX3_QUALITY_GATE_FAILED"
            )
        ),
    )
