from __future__ import annotations

from typing import Optional

from .final_gate import evaluate_final_real_gate
from .human_approval import HumanApprovalConfig, evaluate_human_approval
from .local_real_runner import RealRunner, run_box3_real_enablement_smoke
from .real_contracts import Box3RealRuntimeEnvelope, Box3RealVerdict, sha256_text, stable_json_digest
from .real_grounding import extract_claims, extract_evidence_units, ground_claims, summarize_grounding
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
    config = config or Box3RealRunnerConfig.product_default()
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
            # 박스 3 real follow-up v1.2 정정 (2026-06-04): 본진 Verdict required 필드 모두 채움.
            schema_version="box3.real_verdict.v1_2",
            request_id=envelope.request_id,
            request_digest=envelope.request_digest,
            status=decision.status,
            draft_text=None,
            draft_digest=None,
            citations=[],
            claim_verdicts=[],
            metrics={
                "unsupported_count": metrics.unsupported_count,
                "no_evidence_count": metrics.no_evidence_count,
                "citation_accuracy": metrics.citation_accuracy,
                "format_compliance": metrics.format_compliance,
                "style_compliance": metrics.style_compliance,
                "table_figure_coverage": metrics.table_figure_coverage,
            },
            needs_review=False,
            fail_class=decision.fail_class,
            model_chain=list(envelope.model_chain),
            asset_manifest_digest=asset_verdict.asset_manifest_digest,
            real_runner_executed=False,
            contract_only=False,
            real_claim_allowed=False,
            stage_trace=stage_trace + [c.to_dict() for c in decision.conditions],
            human_approval_required=True,
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

    # 박스 3 real follow-up v1.2 정정: 본진 ground_claims 는 list[ClaimVerdict] 반환,
    # summary 는 별도 함수 summarize_grounding (test_ground_claims_returns_list_not_tuple_and_summary_is_separate).
    # 본진 약화 0 — pipeline 본문이 tuple unpacking 하던 결함을 list + 별도 summary 호출로 정정.
    verdicts = ground_claims(claims, evidence_units) if claims else []
    grounding_summary = summarize_grounding(verdicts) if verdicts else None
    stage_trace.append({
        "stage": "claim_grounding",
        "passed": bool(verdicts) and (grounding_summary.unsupported_claim_count == 0 if grounding_summary else False),
        "unsupported_count": grounding_summary.unsupported_claim_count if grounding_summary else 0,
        "no_evidence_count": grounding_summary.no_evidence_claim_count if grounding_summary else 0,
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

    # Codex HOLD 정정 (2026-06-03, PR #775 → 2026-06-04, PR #776 재정정): Box3RealStatus
    # Literal SSOT 6 정합 — response_draft 허용 set 을 본진 Literal 안에서만 구성한다.
    # 이전 set 안의 비정본 상태 문자열(Literal 부재 라벨)은 status 라벨 drift 였다. 본
    # 정정에서 inline set 으로 Literal 정합 status 만 허용 (정적 분석/grep 검증 가능):
    #   - REAL_CANDIDATE: 9조건 + approval 미충족 (정직 candidate).
    #   - PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL: 9조건 + approval 충족 (PASS).
    response_draft = (
        draft_text
        if decision.status in {"REAL_CANDIDATE", "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL"}
        else None
    )
    draft_digest = sha256_text(draft_text) if draft_text else None
    citations = []
    for unit in evidence_units:
        citations.append({
            "source_digest": unit.source_digest,
            "evidence_digest": unit.evidence_digest,
            "evidence_kind": unit.kind,
            "span_label": "runtime_only",
        })
    # 박스 3 real follow-up v1.2 정정 (2026-06-04): 본진 Verdict required 필드 모두 채움.
    return Box3RealVerdict(
        schema_version="box3.real_verdict.v1_2",
        request_id=envelope.request_id,
        request_digest=envelope.request_digest,
        status=decision.status,
        draft_text=response_draft,
        draft_digest=draft_digest if response_draft else None,
        citations=citations,
        claim_verdicts=[v.to_dict() if hasattr(v, "to_dict") else v for v in verdicts],
        metrics={
            "unsupported_count": metrics.unsupported_count,
            "no_evidence_count": metrics.no_evidence_count,
            "citation_accuracy": metrics.citation_accuracy,
            "format_compliance": metrics.format_compliance,
            "style_compliance": metrics.style_compliance,
            "table_figure_coverage": metrics.table_figure_coverage,
            "factual_claim_count": metrics.factual_claim_count,
            "unsupported_claim_rate": metrics.unsupported_claim_rate,
            "no_evidence_claim_rate": metrics.no_evidence_claim_rate,
            "supported_count": metrics.supported_count,
        },
        needs_review=decision.status in {"REAL_CANDIDATE", "BLOCKED"} and decision.real_claim_allowed is False,
        fail_class=decision.fail_class,
        model_chain=list(envelope.model_chain),
        asset_manifest_digest=asset_verdict.asset_manifest_digest,
        real_runner_executed=runner_result.ok,
        contract_only=not decision.real_claim_allowed,
        real_claim_allowed=decision.real_claim_allowed,
        stage_trace=stage_trace,
        human_approval_required=decision.human_approval_required,
        runner_asset_digest=asset_verdict.runner_asset_digest,
        human_approval_digest=approval.config_digest,
    )
