from __future__ import annotations

from typing import Optional

from .final_gate import evaluate_final_real_gate
from .human_approval import HumanApprovalConfig, evaluate_human_approval
from .local_real_runner import RealRunner, run_box3_real_enablement_smoke
from .real_contracts import Box3RealRuntimeEnvelope, Box3RealVerdict, sha256_text, stable_json_digest
from .real_grounding import extract_claims, extract_evidence_units, ground_claims
from .real_metrics import compute_claim_metrics, estimate_format_compliance, estimate_style_compliance
from .real_runner_assets import Box3RealRunnerConfig, verify_box3_real_runner_assets


def run_box3_real_enablement_pipeline(
    envelope: Box3RealRuntimeEnvelope,
    *,
    config: Optional[Box3RealRunnerConfig] = None,
    asset_manifest: Optional[dict] = None,
    human_approval_config: Optional[HumanApprovalConfig] = None,
    fixed_eval_pass: bool = False,
    runner: Optional[RealRunner] = None,
) -> Box3RealVerdict:
    config = config or Box3RealRunnerConfig.from_env()
    stage_trace = []

    asset_verdict = verify_box3_real_runner_assets(config, helper_manifest=asset_manifest)
    stage_trace.append({"stage": "asset_inventory", "passed": asset_verdict.allowed, "fail_class": asset_verdict.fail_class})

    evidence_units = extract_evidence_units(envelope.reference_docs_runtime_only)
    envelope.evidence_units_runtime = evidence_units
    stage_trace.append({"stage": "evidence_extraction", "passed": bool(evidence_units), "evidence_count": len(evidence_units)})

    if not envelope.policy_gate_allowed:
        metrics = compute_claim_metrics([], format_compliance=0.0, style_compliance=0.0, evidence_units=evidence_units)
        approval = evaluate_human_approval(human_approval_config, expected_scope_digest=envelope.request_digest)
        decision = evaluate_final_real_gate(
            asset_verdict=asset_verdict,
            policy_allowed=False,
            runner_generated=False,
            runner_fail_class="BLOCK_POLICY_GATE",
            evidence_count=len(evidence_units),
            claim_count=0,
            metrics=metrics,
            fixed_eval_pass=False,
            human_approval=approval,
        )
        return Box3RealVerdict(
            status=decision.status,
            request_id=envelope.request_id,
            request_digest=envelope.request_digest,
            draft_text=None,
            draft_digest=None,
            claim_verdicts=[],
            citations=[],
            metrics=metrics,
            stage_trace=stage_trace + [c.to_dict() for c in decision.conditions],
            fail_class=decision.fail_class,
            real_claim_allowed=False,
            human_approval_required=True,
            asset_manifest_digest=asset_verdict.asset_manifest_digest,
            runner_asset_digest=asset_verdict.runner_asset_digest,
            human_approval_digest=approval.config_digest,
        )

    runner_result = run_box3_real_enablement_smoke(envelope, config, runner=runner if asset_verdict.allowed or runner is not None else None)
    stage_trace.append({
        "stage": "draft_runner",
        "passed": runner_result.ok,
        "fail_class": runner_result.fail_class,
        "latency_ms": runner_result.latency_ms,
        "tokens_estimated": runner_result.tokens_estimated,
        "load_ms": runner_result.load_ms,
        "peak_memory_mb": runner_result.peak_memory_mb,
    })

    draft_text = runner_result.draft_text or ""
    claims = extract_claims(draft_text) if draft_text else []
    envelope.draft_claims_runtime = claims
    stage_trace.append({"stage": "claim_extraction", "passed": bool(claims), "claim_count": len(claims)})

    verdicts, grounding_summary = ground_claims(claims, evidence_units) if claims else ([], None)
    stage_trace.append({
        "stage": "claim_grounding",
        "passed": bool(verdicts) and (grounding_summary.unsupported_count == 0 if grounding_summary else False),
        "unsupported_count": grounding_summary.unsupported_count if grounding_summary else 0,
        "no_evidence_count": grounding_summary.no_evidence_count if grounding_summary else 0,
    })

    format_score = estimate_format_compliance(draft_text) if draft_text else 0.0
    style_score = estimate_style_compliance(draft_text) if draft_text else 0.0
    metrics = compute_claim_metrics(verdicts, format_compliance=format_score, style_compliance=style_score, evidence_units=evidence_units)
    stage_trace.append({"stage": "format_style", "format_compliance": format_score, "style_compliance": style_score, "table_figure_coverage": metrics.table_figure_coverage})

    approval = evaluate_human_approval(human_approval_config, expected_scope_digest=envelope.request_digest)
    decision = evaluate_final_real_gate(
        asset_verdict=asset_verdict,
        policy_allowed=True,
        runner_generated=runner_result.ok,
        runner_fail_class=runner_result.fail_class,
        evidence_count=len(evidence_units),
        claim_count=len(claims),
        metrics=metrics,
        fixed_eval_pass=fixed_eval_pass,
        human_approval=approval,
    )
    stage_trace.append({"stage": "final_gate", "status": decision.status, "real_claim_allowed": decision.real_claim_allowed, "fail_class": decision.fail_class})
    stage_trace.extend(c.to_dict() for c in decision.conditions)

    # Codex HOLD 정정 (2026-06-03, PR #775): Box3RealStatus Literal 정합 — 이전 임시 라벨을
    # SSOT 라벨 PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL 로 통일 (drift 0).
    response_draft = (
        draft_text
        if decision.status
        in {"REAL_CANDIDATE", "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL", "RUNNER_SMOKE_PASS"}
        else None
    )
    draft_digest = sha256_text(draft_text) if draft_text else None
    citations = []
    for unit in evidence_units:
        citations.append({
            "source_digest": unit.source_digest,
            "evidence_digest": unit.evidence_digest,
            "evidence_kind": unit.evidence_kind,
            "span_label": "runtime_only",
        })
    return Box3RealVerdict(
        status=decision.status,
        request_id=envelope.request_id,
        request_digest=envelope.request_digest,
        draft_text=response_draft,
        draft_digest=draft_digest if response_draft else None,
        claim_verdicts=verdicts,
        citations=citations,
        metrics=metrics,
        stage_trace=stage_trace,
        fail_class=decision.fail_class,
        real_claim_allowed=decision.real_claim_allowed,
        human_approval_required=decision.human_approval_required,
        asset_manifest_digest=asset_verdict.asset_manifest_digest,
        runner_asset_digest=asset_verdict.runner_asset_digest,
        human_approval_digest=approval.config_digest,
    )
