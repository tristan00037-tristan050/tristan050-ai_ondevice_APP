"""Box3 real 융합 — 7단계 fail-closed real 파이프라인(단일 계약 출력).

- 베이스: codex run_box3_real_followup(stage_trace 관찰성 + 골격 PR #770
  asset_manifest 재사용: manifest_allows_real / manifest_block_reason).
- 흡수: maindev _call_runner_with_timeout(ThreadPoolExecutor 타임아웃) + 7단계
  fail-closed 게이트, alg 단계별 contract_only 분기 + table_figure coverage.

7단계 고정: asset_inventory → helper7_evidence_extraction → draft_runner(timeout)
→ claim_extraction → helper4_claim_grounding → helper3_helper8_format_style →
final_real_gate. 출력 verdict 는 stage_trace(audit) + contract_only +
real_claim_allowed 을 담는다. asset 이 PENDING 이면 real claim 은 닫힌다(contract_only).
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from typing import Any, Callable

from .asset_manifest import (
    build_contract_only_asset_manifest,
    manifest_allows_real,
    manifest_block_reason,
)
from .real_contracts import (
    Box3RealAuditRecord,
    Box3RealRuntimeEnvelope,
    Box3RealVerdict,
    assert_audit_record_is_digest_only,
    build_audit_record,
    new_request_id,
    sha256_text,
)
from .real_fail_class import (
    ASSET_INTERFACE_PENDING,
    BLOCK_BOX3_REAL_RUNNER_ERROR,
    BLOCK_BOX3_REAL_RUNNER_MISSING,
    BLOCK_BOX3_REAL_RUNNER_TIMEOUT,
    BLOCK_BOX3_REAL_SECURITY_RISK,
    BLOCK_CLAIM_EXTRACTION_EMPTY,
    BLOCK_EVIDENCE_EXTRACTION_FAILED,
)
from .real_grounding import extract_claims, extract_evidence_units, ground_claims, summarize_grounding
from .real_metrics import build_metrics, fixed_eval_metric_pass, metric_fail_class
from .security import Box3SecurityError, assert_no_raw_persistence, stable_json_digest

RealRunner = Callable[[Box3RealRuntimeEnvelope], str]
SCHEMA_VERDICT = "box3.real_verdict.v1_2"
_REAL_DRAFT_EMPTY = "BLOCK_BOX3_REAL_DRAFT_EMPTY"

_ZERO_METRICS: dict[str, Any] = {
    "unsupported_claim_rate": 0.0,
    "no_evidence_claim_rate": 0.0,
    "citation_accuracy": 0.0,
    "format_compliance": 0.0,
    "style_compliance": 0.0,
    "table_figure_coverage": 0.0,
    "factual_claim_count": 0,
    "unsupported_count": 0,
    "no_evidence_count": 0,
    "supported_count": 0,
}


@dataclass(frozen=True)
class Box3RealPipelineConfig:
    timeout_sec: float = 30.0
    fixed_eval_pass: bool = False
    allow_pass_box3_real_after_human_approval: bool = False


def _stage(name: str, status: str, fail_class: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"stage": name, "status": status, "fail_class": fail_class}
    payload.update(extra)
    assert_no_raw_persistence(payload)
    return payload


def _call_runner_with_timeout(runner: RealRunner, envelope: Box3RealRuntimeEnvelope, timeout_sec: float) -> str:
    # `with ThreadPoolExecutor` 의 __exit__ 는 shutdown(wait=True) 라 timeout 후에도 hung
    # 러너 종료를 기다려 sidecar 가 블로킹된다. shutdown(wait=False, cancel_futures=True)로
    # 즉시 반환해 timeout 을 실질 적용한다(러너 스레드는 백그라운드에 남지만 응답은 막지 않음).
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(runner, envelope)
    try:
        return str(future.result(timeout=timeout_sec))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _finalize(
    envelope: Box3RealRuntimeEnvelope,
    *,
    status: str,
    fail_class: str | None,
    manifest_digest: str,
    stage_trace: list[dict[str, Any]],
    real_runner_executed: bool,
    contract_only: bool,
    real_claim_allowed: bool,
    metrics: dict[str, Any] | None = None,
    claim_verdicts: list[dict[str, Any]] | None = None,
    citations: list[dict[str, str]] | None = None,
    draft_text: str | None = None,
) -> tuple[Box3RealVerdict, Box3RealAuditRecord]:
    metric_payload = metrics or dict(_ZERO_METRICS)
    draft_digest = sha256_text(draft_text) if draft_text else None
    verdict = Box3RealVerdict(
        schema_version=SCHEMA_VERDICT,
        request_id=envelope.request_id,
        status=status,  # type: ignore[arg-type]
        draft_text=draft_text,
        draft_digest=draft_digest,
        citations=citations or [],
        claim_verdicts=claim_verdicts or [],
        metrics=metric_payload,
        needs_review=status == "needs_review",
        fail_class=fail_class,
        model_chain=envelope.model_chain,
        asset_manifest_digest=manifest_digest,
        real_runner_executed=real_runner_executed,
        contract_only=contract_only,
        real_claim_allowed=real_claim_allowed,
    )
    audit = build_audit_record(envelope=envelope, verdict=verdict, stage_trace=stage_trace)
    # fail-closed 영속 검증 — raw/path/secret/PII 누출 시 예외.
    verdict.to_persistable_dict()
    assert_audit_record_is_digest_only(audit)
    return verdict, audit


def _run(
    envelope: Box3RealRuntimeEnvelope,
    *,
    asset_manifest: dict[str, Any] | None,
    real_model_runner: RealRunner | None,
    cfg: Box3RealPipelineConfig,
) -> tuple[Box3RealVerdict, Box3RealAuditRecord]:
    stage_trace: list[dict[str, Any]] = []
    manifest = asset_manifest if asset_manifest is not None else build_contract_only_asset_manifest()
    manifest_digest = stable_json_digest(manifest) if isinstance(manifest, dict) else sha256_text("invalid-manifest")

    # 입력 런타임 안전성(DLP) 사전 검증 — 모든 종료 경로(contract_only 포함)가 raw/path/
    # secret/PII 누출에 fail-closed 가 되도록 asset 게이트보다 먼저 검사한다.
    try:
        envelope.assert_runtime_safe()
    except Box3SecurityError:
        stage_trace.append(_stage("input_runtime_safety", "blocked", BLOCK_BOX3_REAL_SECURITY_RISK))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_BOX3_REAL_SECURITY_RISK, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=False, contract_only=False, real_claim_allowed=False)

    # Stage 1 — asset inventory (골격 #770 manifest 재사용).
    manifest_fail = manifest_block_reason(manifest)
    if manifest_fail:
        stage_trace.append(_stage("asset_inventory", "blocked", manifest_fail))
        return _finalize(envelope, status="blocked", fail_class=manifest_fail, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=False, contract_only=False, real_claim_allowed=False)
    if not manifest_allows_real(manifest):
        # 자산 인벤토리 PENDING — real claim 을 닫고 contract_only 로 정직하게 보류.
        stage_trace.append(_stage("asset_inventory", "contract_only", ASSET_INTERFACE_PENDING))
        return _finalize(envelope, status="contract_only", fail_class=ASSET_INTERFACE_PENDING, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=False, contract_only=True, real_claim_allowed=False)
    stage_trace.append(_stage("asset_inventory", "pass"))

    # Stage 2 — helper7 evidence extraction (입력 DLP 는 위에서 이미 fail-closed 검증됨).
    envelope.evidence_units_runtime = extract_evidence_units(envelope.reference_text_runtime_only)
    if not envelope.evidence_units_runtime:
        stage_trace.append(_stage("helper7_evidence_extraction", "blocked", BLOCK_EVIDENCE_EXTRACTION_FAILED))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_EVIDENCE_EXTRACTION_FAILED, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=False, contract_only=False, real_claim_allowed=False)
    stage_trace.append(_stage("helper7_evidence_extraction", "pass",
                              evidence_unit_count=len(envelope.evidence_units_runtime), output_digest_only=True))

    # Stage 3 — real runner (timeout). 러너와 asset pass 가 모두 있어야 real; 아니면 fail-closed.
    if real_model_runner is None:
        stage_trace.append(_stage("draft_runner", "blocked", BLOCK_BOX3_REAL_RUNNER_MISSING))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_BOX3_REAL_RUNNER_MISSING, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=False, contract_only=False, real_claim_allowed=False)
    try:
        envelope.draft_text_runtime = _call_runner_with_timeout(real_model_runner, envelope, cfg.timeout_sec)
    except concurrent.futures.TimeoutError:
        stage_trace.append(_stage("draft_runner", "blocked", BLOCK_BOX3_REAL_RUNNER_TIMEOUT))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_BOX3_REAL_RUNNER_TIMEOUT, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False)
    except Exception:
        # 러너의 일반 추론/모델 예외도 fail-closed blocked verdict 로 변환(미처리 500 방지).
        # 예외 메시지는 원문 누출 위험이 있어 reason code 만 기록한다.
        stage_trace.append(_stage("draft_runner", "blocked", BLOCK_BOX3_REAL_RUNNER_ERROR))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_BOX3_REAL_RUNNER_ERROR, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False)
    if not isinstance(envelope.draft_text_runtime, str) or not envelope.draft_text_runtime.strip():
        stage_trace.append(_stage("draft_runner", "blocked", _REAL_DRAFT_EMPTY))
        return _finalize(envelope, status="blocked", fail_class=_REAL_DRAFT_EMPTY, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False)
    try:
        envelope.assert_runtime_safe()
    except Box3SecurityError:
        stage_trace.append(_stage("draft_runner", "blocked", BLOCK_BOX3_REAL_SECURITY_RISK))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_BOX3_REAL_SECURITY_RISK, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False)
    stage_trace.append(_stage("draft_runner", "pass", draft_digest=sha256_text(envelope.draft_text_runtime)))

    # Stage 4 — claim extraction. 사실 claim 0 이면 분모 0 → fail-closed.
    envelope.draft_claims_runtime = extract_claims(envelope.draft_text_runtime or "")
    factual_count = sum(1 for claim in envelope.draft_claims_runtime if claim.is_factual)
    if factual_count == 0:
        stage_trace.append(_stage("claim_extraction", "blocked", BLOCK_CLAIM_EXTRACTION_EMPTY))
        return _finalize(envelope, status="blocked", fail_class=BLOCK_CLAIM_EXTRACTION_EMPTY, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False)
    stage_trace.append(_stage("claim_extraction", "pass", factual_claim_count=factual_count))

    # Stage 5 — helper4 claim grounding + citation 연결.
    claim_verdicts = ground_claims(envelope.draft_claims_runtime, envelope.evidence_units_runtime)
    summary = summarize_grounding(claim_verdicts)
    citations: list[dict[str, str]] = []
    for verdict in claim_verdicts:
        if verdict.support_level == "supported":
            for digest in verdict.evidence_digests:
                unit = next((u for u in envelope.evidence_units_runtime if u.evidence_digest == digest), None)
                if unit:
                    citations.append(unit.citation())
    claim_dicts = [verdict.to_dict() for verdict in claim_verdicts]
    stage_trace.append(_stage(
        "helper4_claim_grounding",
        "pass" if summary.fail_class is None else "blocked",
        summary.fail_class,
        factual_claim_count=summary.factual_claim_count,
        unsupported_claim_rate=summary.unsupported_claim_rate,
        no_evidence_rate=summary.no_evidence_rate,
    ))

    # Stage 6 — helper3/helper8 format·style 지표.
    metrics = build_metrics(
        draft_text=envelope.draft_text_runtime or "",
        verdicts=claim_verdicts,
        evidence_units=envelope.evidence_units_runtime,
        citations=citations,
    )
    metrics_dict = metrics.to_dict()
    format_style_ok = metrics.format_compliance >= 0.85 and metrics.style_compliance >= 0.70
    stage_trace.append(_stage(
        "helper3_helper8_format_style",
        "pass" if format_style_ok else "needs_review",
        None if format_style_ok else "FORMAT_OR_STYLE_BELOW_GATE",
        format_match_score=metrics.format_compliance,
        style_match_score=metrics.style_compliance,
    ))

    # Stage 7 — final gate.
    fail_class = metric_fail_class(metrics)
    if fail_class:
        status = "blocked" if fail_class.startswith("BLOCK_") else "needs_review"
        stage_trace.append(_stage("final_real_gate", status, fail_class, metrics_pass=False))
        return _finalize(envelope, status=status, fail_class=fail_class, manifest_digest=manifest_digest,
                         stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=False,
                         metrics=metrics_dict, claim_verdicts=claim_dicts, citations=citations, draft_text=None)

    stage_trace.append(_stage("final_real_gate", "pass", metrics_pass=True))
    final_real = (
        cfg.fixed_eval_pass
        and cfg.allow_pass_box3_real_after_human_approval
        and fixed_eval_metric_pass(metrics)
    )
    status = "real" if final_real else "real_candidate"
    return _finalize(envelope, status=status, fail_class=None, manifest_digest=manifest_digest,
                     stage_trace=stage_trace, real_runner_executed=True, contract_only=False, real_claim_allowed=final_real,
                     metrics=metrics_dict, claim_verdicts=claim_dicts, citations=citations,
                     draft_text=envelope.draft_text_runtime)


def run_box3_real_pipeline(
    *,
    reference_docs: list[str],
    drafting_request: str,
    format_hint: str = "자유형",
    max_new_tokens: int = 512,
    request_id: str | None = None,
    asset_manifest: dict[str, Any] | None = None,
    real_model_runner: RealRunner | None = None,
    config: Box3RealPipelineConfig | None = None,
) -> tuple[Box3RealVerdict, Box3RealAuditRecord]:
    envelope = Box3RealRuntimeEnvelope(
        request_id=request_id or new_request_id(),
        reference_text_runtime_only=list(reference_docs),
        drafting_request_runtime=drafting_request,
        format_hint=format_hint,
        max_new_tokens=max_new_tokens,
    )
    return _run(envelope, asset_manifest=asset_manifest, real_model_runner=real_model_runner,
                cfg=config or Box3RealPipelineConfig())


def run_box3_real_followup(
    envelope: Box3RealRuntimeEnvelope,
    *,
    asset_manifest: dict[str, Any] | None = None,
    real_model_runner: RealRunner | None = None,
    config: Box3RealPipelineConfig | None = None,
) -> tuple[Box3RealVerdict, Box3RealAuditRecord]:
    """codex 명명 호환 진입점 — 이미 구성된 envelope 로 동일 파이프라인을 실행한다."""
    return _run(envelope, asset_manifest=asset_manifest, real_model_runner=real_model_runner,
                cfg=config or Box3RealPipelineConfig())
