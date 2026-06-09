from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .grounded_prompt import REQUIRED_LABELS
from .v7_abstain_gate import evaluate_abstain_usage
from .v7_asset_manifest import V7AssetVerdict, verify_v7_q4_asset
from .v7_degeneration_gate import evaluate_degeneration
from .v7_fail_class import (
    BLOCK_DEGENERATION_DETECTED,
    BLOCK_PRECONDITION_PR785_NOT_MERGED,
    BLOCK_UNSUPPORTED_CLAIM,
    PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL,
    PARTIAL,
    PARTIAL_BOX3_V7_ABSTAIN_OVERUSE,
    PARTIAL_BOX3_V7_CITATION_LOW,
)
from .v7_preconditions import PreconditionVerdict, verify_pr785_precondition
from .v7_security import assert_digest_only, stable_json_digest

@dataclass(frozen=True)
class V7SmokeMetrics:
    unsupported_count: int
    citation_accuracy: float
    supported_count: int
    table_normal: bool
    raw_saved_zero: bool
    external_send_zero: bool
    production_claim_allowed: bool
    latency_ms: float | None = None
    peak_memory_mb: float | None = None
    memory_backend: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class V7FinalDecision:
    status: str
    real_claim_allowed: bool
    fail_class: str | None
    request_digest: str
    conditions: list[dict[str, Any]]
    metrics_digest: str
    raw_saved_zero: bool = True
    external_send_zero: bool = True
    production_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_digest_only(payload)
        return payload


def section_completeness(draft_text: str) -> float:
    return sum(1 for label in REQUIRED_LABELS if f"{label}:" in draft_text) / len(REQUIRED_LABELS)


def usefulness_gate(draft_text: str, supported_count: int) -> tuple[str, str | None, float]:
    completeness = section_completeness(draft_text)
    if supported_count < 1:
        return PARTIAL, "PARTIAL_SUPPORTED_CLAIM_COUNT_LOW", completeness
    if completeness < 0.67:
        return PARTIAL, "PARTIAL_SECTION_COMPLETENESS_LOW", completeness
    return "PASS", None, completeness


def evaluate_v7_final_gate(
    *,
    draft_text: str,
    metrics: V7SmokeMetrics,
    request_digest: str,
    precondition: PreconditionVerdict | None = None,
    asset_verdict: V7AssetVerdict | None = None,
    human_approval_allowed: bool = False,
) -> V7FinalDecision:
    pre = precondition or verify_pr785_precondition()
    asset = asset_verdict or verify_v7_q4_asset()
    abstain = evaluate_abstain_usage(draft_text)
    degen = evaluate_degeneration(draft_text)
    useful_status, useful_fail, completeness = usefulness_gate(draft_text, metrics.supported_count)
    conditions = [
        {"name": "pr785_precondition", "passed": pre.passed, "fail_class": pre.fail_class},
        {"name": "v7_asset", "passed": asset.allowed, "fail_class": asset.fail_class},
        {"name": "unsupported_zero", "passed": metrics.unsupported_count == 0, "fail_class": BLOCK_UNSUPPORTED_CLAIM if metrics.unsupported_count else None},
        {"name": "degeneration_false", "passed": not degen.detected, "fail_class": degen.fail_class, "ngram_ratio": degen.ngram_ratio},
        {"name": "abstain_valid", "passed": abstain.valid and abstain.fail_class is None, "fail_class": abstain.fail_class, "abstain_ratio": abstain.abstain_ratio},
        {"name": "citation_accuracy", "passed": metrics.citation_accuracy >= 0.95, "fail_class": None if metrics.citation_accuracy >= 0.95 else PARTIAL_BOX3_V7_CITATION_LOW},
        {"name": "section_completeness", "passed": completeness >= 0.67, "fail_class": useful_fail, "section_completeness": round(completeness, 4)},
        {"name": "table_normal", "passed": bool(metrics.table_normal), "fail_class": None if metrics.table_normal else "PARTIAL_TABLE_NORMAL_FALSE"},
        {"name": "raw_external", "passed": metrics.raw_saved_zero and metrics.external_send_zero, "fail_class": None if metrics.raw_saved_zero and metrics.external_send_zero else "BLOCK_RAW_OR_EXTERNAL"},
        {"name": "production_claim_false", "passed": metrics.production_claim_allowed is False, "fail_class": None if metrics.production_claim_allowed is False else "BLOCK_PRODUCTION_CLAIM"},
        {"name": "human_approval", "passed": bool(human_approval_allowed), "fail_class": None if human_approval_allowed else "BLOCK_HUMAN_APPROVAL_MISSING"},
    ]
    blocking = next((c for c in conditions if not c["passed"] and str(c.get("fail_class") or "").startswith("BLOCK_")), None)
    if blocking:
        return _decision(str(blocking["fail_class"]), False, str(blocking["fail_class"]), request_digest, conditions, metrics)
    partial = next((c for c in conditions if not c["passed"]), None)
    if partial:
        return _decision(str(partial.get("fail_class") or PARTIAL), False, str(partial.get("fail_class") or PARTIAL), request_digest, conditions, metrics)
    return _decision(PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL, True, None, request_digest, conditions, metrics)


def _decision(status: str, allowed: bool, fail_class: str | None, request_digest: str, conditions: list[dict[str, Any]], metrics: V7SmokeMetrics) -> V7FinalDecision:
    return V7FinalDecision(status, allowed, fail_class, request_digest, conditions, stable_json_digest(metrics.to_dict()))
