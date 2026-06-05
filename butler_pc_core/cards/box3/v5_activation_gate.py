from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .v5_asset_manifest import manifest_allows_v5_real, V5_MODEL_NAME

@dataclass(frozen=True)
class V5EndpointMetricSnapshot:
    unsupported_count: int
    supported_count: int
    citation_accuracy: float
    format_compliance: float
    style_compliance: float
    table_figure_coverage: float
    degeneration_detected: bool
    abstain_ratio: float
    section_completeness: float
    raw_saved_zero: bool
    external_send_zero: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class V5ActivationDecision:
    status: str
    pass_allowed: bool
    fail_class: str | None
    reason: str
    model_choice: str = V5_MODEL_NAME

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def evaluate_v5_activation_gate(
    *,
    asset_manifest: dict[str, Any],
    metrics: V5EndpointMetricSnapshot,
    regression_passed: bool,
    fixed_eval_passed: bool,
    human_approval_allowed: bool,
) -> V5ActivationDecision:
    if not manifest_allows_v5_real(asset_manifest):
        asset = asset_manifest.get("asset", {}) if isinstance(asset_manifest, dict) else {}
        fail = asset.get("fail_class") or "BLOCK_MODEL_ASSET_SHA_MISMATCH"
        status = asset_manifest.get("status") if isinstance(asset_manifest, dict) else "BLOCKED"
        if isinstance(status, str) and status.startswith("PARTIAL_"):
            return V5ActivationDecision("PARTIAL", False, fail, "v5 asset manifest is not ready")
        return V5ActivationDecision("BLOCK", False, fail, "v5 asset manifest did not pass")
    if metrics.degeneration_detected:
        return V5ActivationDecision("BLOCK", False, "BLOCK_DEGENERATION", "degeneration gate failed")
    if metrics.unsupported_count > 0:
        return V5ActivationDecision("BLOCK", False, "BLOCK_UNSUPPORTED_CLAIM", "unsupported claim detected")
    if metrics.citation_accuracy < 0.95:
        return V5ActivationDecision("PARTIAL", False, "CITATION_ACCURACY_BELOW_GATE", "citation accuracy below 0.95")
    if metrics.supported_count < 1 or metrics.section_completeness < 0.67 or metrics.abstain_ratio > 0.60:
        return V5ActivationDecision("PARTIAL", False, "PARTIAL_SUMMARY_TOO_WEAK", "usefulness gate did not pass")
    if metrics.format_compliance < 0.85 or metrics.style_compliance < 0.70 or metrics.table_figure_coverage < 0.70:
        return V5ActivationDecision("PARTIAL", False, "NEEDS_REVIEW_FORMAT_STYLE_GATE", "format/style/table gate did not pass")
    if not metrics.raw_saved_zero or not metrics.external_send_zero:
        return V5ActivationDecision("BLOCK", False, "BLOCK_RAW_PATH_SECRET_LEAK", "security flags failed")
    if not regression_passed:
        return V5ActivationDecision("PARTIAL", False, "REGRESSION_PENDING", "regression not measured or failed")
    if not fixed_eval_passed:
        return V5ActivationDecision("REAL_CANDIDATE", False, "FIXED_EVAL_PENDING", "fixed eval not yet passed")
    if not human_approval_allowed:
        return V5ActivationDecision("REAL_CANDIDATE", False, "BLOCK_HUMAN_APPROVAL_MISSING", "human approval not sealed")
    return V5ActivationDecision("PASS_BOX3_V5_CANONICAL_APPLY", True, None, "all v5 gates passed")
