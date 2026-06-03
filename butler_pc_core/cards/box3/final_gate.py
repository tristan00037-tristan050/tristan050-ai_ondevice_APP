from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, List, Optional

from .human_approval import HumanApprovalVerdict
from .real_contracts import Box3RealMetrics, Box3RealStatus
from .real_fail_class import (
    BLOCK_ASSET_INVENTORY_NOT_PASS,
    BLOCK_FINAL_GATE_UNSUPPORTED,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    BLOCK_POLICY_GATE,
    BLOCK_RUNNER_ERROR,
    FIXED_EVAL_PENDING,
    NEEDS_REVIEW_FORMAT_STYLE_GATE,
    NEEDS_REVIEW_NO_EVIDENCE_CLAIMS,
)
from .real_runner_assets import Box3RealRunnerAssetVerdict


@dataclass(frozen=True)
class GateConditionResult:
    name: str
    passed: bool
    fail_class: Optional[str]
    detail_digest: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FinalGateDecision:
    status: Box3RealStatus
    real_claim_allowed: bool
    fail_class: Optional[str]
    human_approval_required: bool
    conditions: List[GateConditionResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "real_claim_allowed": self.real_claim_allowed,
            "fail_class": self.fail_class,
            "human_approval_required": self.human_approval_required,
            "conditions": [item.to_dict() for item in self.conditions],
        }


def evaluate_final_real_gate(
    *,
    asset_verdict: Box3RealRunnerAssetVerdict,
    policy_allowed: bool,
    runner_generated: bool,
    runner_fail_class: Optional[str],
    evidence_count: int,
    claim_count: int,
    metrics: Box3RealMetrics,
    fixed_eval_pass: bool,
    human_approval: HumanApprovalVerdict,
) -> FinalGateDecision:
    conditions = [
        GateConditionResult("asset_inventory", asset_verdict.allowed, asset_verdict.fail_class),
        GateConditionResult("policy_gate", policy_allowed, None if policy_allowed else BLOCK_POLICY_GATE),
        GateConditionResult("runner_asset_sha", asset_verdict.allowed, asset_verdict.fail_class),
        GateConditionResult("reference_evidence", evidence_count >= 1, None if evidence_count >= 1 else "BLOCK_EVIDENCE_MISSING"),
        GateConditionResult("real_runner_generate", runner_generated, runner_fail_class if not runner_generated else None),
        GateConditionResult(
            "claim_grounding_metric",
            metrics.unsupported_count == 0 and metrics.no_evidence_claim_rate <= 0.05 and metrics.citation_accuracy >= 0.95,
            BLOCK_FINAL_GATE_UNSUPPORTED if metrics.unsupported_count else (NEEDS_REVIEW_NO_EVIDENCE_CLAIMS if metrics.no_evidence_claim_rate > 0.05 else None),
        ),
        GateConditionResult(
            "format_style",
            metrics.format_compliance >= 0.85 and metrics.style_compliance >= 0.70 and metrics.table_figure_coverage >= 0.70,
            None if metrics.format_compliance >= 0.85 and metrics.style_compliance >= 0.70 and metrics.table_figure_coverage >= 0.70 else NEEDS_REVIEW_FORMAT_STYLE_GATE,
        ),
        GateConditionResult("fixed_eval_40", fixed_eval_pass, None if fixed_eval_pass else FIXED_EVAL_PENDING),
        GateConditionResult("human_approval", human_approval.allowed, human_approval.fail_class),
    ]

    blocking = next((c for c in conditions[:7] if not c.passed and c.fail_class and c.fail_class.startswith("BLOCK_")), None)
    if blocking is not None:
        return FinalGateDecision("BLOCKED", False, blocking.fail_class, True, conditions)

    if metrics.unsupported_count > 0:
        return FinalGateDecision("BLOCKED", False, BLOCK_FINAL_GATE_UNSUPPORTED, True, conditions)
    if not runner_generated:
        return FinalGateDecision("ASSET_INVENTORY_PASS" if asset_verdict.allowed else "CONTRACT_ONLY", False, runner_fail_class or BLOCK_RUNNER_ERROR, True, conditions)

    if not fixed_eval_pass:
        return FinalGateDecision("REAL_CANDIDATE", False, FIXED_EVAL_PENDING, True, conditions)

    if not human_approval.allowed:
        # Missing approval is a candidate gate; kill/revoke/expired are hard blocks.
        if human_approval.fail_class in {BLOCK_HUMAN_APPROVAL_KILL_SWITCH, "BLOCK_HUMAN_APPROVAL_REVOKED", "BLOCK_HUMAN_APPROVAL_EXPIRED"}:
            return FinalGateDecision("BLOCKED", False, human_approval.fail_class, True, conditions)
        return FinalGateDecision("REAL_CANDIDATE", False, human_approval.fail_class, True, conditions)

    if all(c.passed for c in conditions):
        # Codex HOLD 정정 (2026-06-03, PR #775): Box3RealStatus Literal 정합 — 모든 9조건 +
        # human approval 통과 시 SSOT 라벨 PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL 반환.
        # 이전 임시 라벨은 Literal 에 부재로 상태 드리프트 야기.
        return FinalGateDecision(
            "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL", True, None, False, conditions
        )
    soft = next((c for c in conditions if not c.passed), None)
    return FinalGateDecision("REAL_CANDIDATE", False, soft.fail_class if soft else None, True, conditions)
