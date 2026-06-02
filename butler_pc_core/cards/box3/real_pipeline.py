from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .adapters.helper3_format_adapter import apply_format_contract
from .adapters.helper8_style_adapter import apply_style_contract
from .asset_manifest import build_contract_only_asset_manifest, manifest_allows_real, manifest_block_reason
from .claim_grounding import ground_claims
from .real_contract import (
    Box3RealAuditRecord,
    Box3RealPipelineOutput,
    Box3RealRuntimeEnvelope,
    Box3RealVerdict,
)
from .real_metrics import build_real_metrics, metric_fail_class
from .security import assert_no_raw_persistence, assert_runtime_text_safe, sha256_digest


RealModelRunner = Callable[[Box3RealRuntimeEnvelope], str]


def _stage(name: str, status: str, fail_class: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"stage": name, "status": status, "fail_class": fail_class}
    payload.update(extra)
    assert_no_raw_persistence(payload)
    return payload


def _blocked_output(
    *,
    envelope: Box3RealRuntimeEnvelope,
    status: str,
    fail_class: str,
    stage_trace: list[dict[str, Any]],
    metrics: dict[str, Any] | None = None,
    claim_verdicts: list[dict[str, Any]] | None = None,
    draft_digest: str | None = None,
) -> Box3RealPipelineOutput:
    verdict = Box3RealVerdict(
        schema_version="box3.real_verdict.v1_2",
        status=status,  # type: ignore[arg-type]
        draft_text=None,
        draft_digest=draft_digest,
        claim_verdicts=claim_verdicts or [],
        metrics=metrics or {},
        fail_class=fail_class,
        contract_only=status == "contract_only",
        real_claim_allowed=False,
        external_send_zero=True,
        raw_saved_zero=True,
    )
    audit = Box3RealAuditRecord(
        schema_version="box3.real_audit.v1_2",
        status=status,  # type: ignore[arg-type]
        request_digest=envelope.request_digest,
        reference_digests=list(envelope.reference_digests),
        company_format_digest=envelope.company_format_digest,
        draft_digest=draft_digest,
        stage_trace=stage_trace,
        fail_class=fail_class,
        external_send_zero=True,
        raw_saved_zero=True,
    )
    output = Box3RealPipelineOutput(verdict=verdict, audit=audit)
    output.to_persistable_dict()
    return output


def run_box3_real_followup(
    envelope: Box3RealRuntimeEnvelope,
    *,
    asset_manifest: dict[str, Any] | None = None,
    real_model_runner: RealModelRunner | None = None,
    fixed_eval_sample_count: int = 0,
    table_figure_grounding_score: float = 1.0,
) -> Box3RealPipelineOutput:
    """Run the Box 3 real follow-up pipeline with fail-closed gates.

    The runner receives raw text only through Box3RealRuntimeEnvelope in memory.
    Persisted verdict/audit records carry only digests and metrics.
    """

    stage_trace: list[dict[str, Any]] = []
    manifest = asset_manifest or build_contract_only_asset_manifest()
    manifest_fail = manifest_block_reason(manifest)
    if manifest_fail:
        stage_trace.append(_stage("asset_inventory", "blocked", manifest_fail))
        return _blocked_output(
            envelope=envelope,
            status="blocked",
            fail_class=manifest_fail,
            stage_trace=stage_trace,
        )
    if not manifest_allows_real(manifest):
        stage_trace.append(_stage("asset_inventory", "contract_only", "ASSET_INTERFACE_PENDING"))
        return _blocked_output(
            envelope=envelope,
            status="contract_only",
            fail_class="ASSET_INTERFACE_PENDING",
            stage_trace=stage_trace,
        )
    stage_trace.append(_stage("asset_inventory", "pass"))

    if not envelope.reference_texts:
        stage_trace.append(_stage("helper7_evidence_extraction", "needs_review", "NO_EVIDENCE_UNITS"))
        return _blocked_output(
            envelope=envelope,
            status="needs_review",
            fail_class="NO_EVIDENCE_UNITS",
            stage_trace=stage_trace,
        )

    if real_model_runner is None:
        stage_trace.append(_stage("draft_runner", "blocked", "BLOCK_REAL_MODEL_RUNNER_MISSING"))
        return _blocked_output(
            envelope=envelope,
            status="blocked",
            fail_class="BLOCK_REAL_MODEL_RUNNER_MISSING",
            stage_trace=stage_trace,
        )

    stage_trace.append(
        _stage(
            "helper7_evidence_extraction",
            "pass",
            evidence_unit_count=len(envelope.reference_digests),
            output_digest_only=True,
        )
    )
    start = time.time()
    draft_text = real_model_runner(envelope)
    load_time_ms = int((time.time() - start) * 1000)
    if not isinstance(draft_text, str) or not draft_text.strip():
        stage_trace.append(_stage("draft_runner", "blocked", "REAL_DRAFT_EMPTY", duration_ms=load_time_ms))
        return _blocked_output(
            envelope=envelope,
            status="blocked",
            fail_class="REAL_DRAFT_EMPTY",
            stage_trace=stage_trace,
        )
    assert_runtime_text_safe(draft_text)
    draft_digest = sha256_digest(draft_text)
    stage_trace.append(_stage("draft_runner", "pass", duration_ms=load_time_ms, draft_digest=draft_digest))

    claim_verdicts, claim_summary = ground_claims(
        draft_text=draft_text,
        evidence_texts=list(envelope.reference_texts),
        evidence_digests=list(envelope.reference_digests),
    )
    claim_dicts = [item.to_dict() for item in claim_verdicts]
    stage_trace.append(
        _stage(
            "helper4_claim_grounding",
            "pass" if claim_summary.fail_class is None else "blocked",
            claim_summary.fail_class,
            factual_claim_count=claim_summary.factual_claim_count,
            unsupported_claim_rate=claim_summary.unsupported_claim_rate,
            no_evidence_rate=claim_summary.no_evidence_rate,
        )
    )

    format_result = apply_format_contract(draft_text)
    style_result = apply_style_contract(draft_text)
    metrics = build_real_metrics(
        claim_summary=claim_summary,
        format_result=format_result,
        style_result=style_result,
        fixed_eval_sample_count=fixed_eval_sample_count,
        table_figure_grounding_score=table_figure_grounding_score,
    )
    stage_trace.append(
        _stage(
            "helper3_helper8_format_style",
            "pass" if format_result["required_sections_present"] and style_result["forbidden_style_zero"] else "blocked",
            None if format_result["required_sections_present"] and style_result["forbidden_style_zero"] else "FORMAT_OR_STYLE_GATE_FAILED",
            format_match_score=format_result["format_match_score"],
            style_match_score=style_result["style_match_score"],
        )
    )

    fail_class = claim_summary.fail_class or metric_fail_class(metrics)
    if fail_class:
        status = "blocked" if fail_class.startswith("BLOCK_") else "needs_review"
        stage_trace.append(_stage("final_real_gate", status, fail_class, metrics_pass=False))
        return _blocked_output(
            envelope=envelope,
            status=status,
            fail_class=fail_class,
            stage_trace=stage_trace,
            metrics=metrics,
            claim_verdicts=claim_dicts,
            draft_digest=draft_digest,
        )

    stage_trace.append(_stage("final_real_gate", "pass", metrics_pass=True))
    verdict = Box3RealVerdict(
        schema_version="box3.real_verdict.v1_2",
        status="real",
        draft_text=draft_text,
        draft_digest=draft_digest,
        claim_verdicts=claim_dicts,
        metrics=metrics,
        fail_class=None,
        contract_only=False,
        real_claim_allowed=True,
        external_send_zero=True,
        raw_saved_zero=True,
    )
    audit = Box3RealAuditRecord(
        schema_version="box3.real_audit.v1_2",
        status="real",
        request_digest=envelope.request_digest,
        reference_digests=list(envelope.reference_digests),
        company_format_digest=envelope.company_format_digest,
        draft_digest=draft_digest,
        stage_trace=stage_trace,
        fail_class=None,
        external_send_zero=True,
        raw_saved_zero=True,
    )
    output = Box3RealPipelineOutput(verdict=verdict, audit=audit)
    output.to_persistable_dict()
    return output
