from __future__ import annotations

from typing import Any

from .actual_contracts import Box3ActualOperationVerdict, Box3ActualRuntimeEnvelope, sha256_text
from .actual_fail_class import (
    ASSET_INVENTORY_PASS,
    BLOCKED,
    BLOCK_POLICY_GATE,
    FIXED_EVAL_PENDING,
    PARTIAL_BGE_M3_FALLBACK_USED,
    PARTIAL_EMBEDDER_UNAVAILABLE,
    PARTIAL_HELPER_SDK_UNAVAILABLE,
    PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED,
    PARTIAL_REAL_ASSET_VOLUME_MISSING,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
    PASS_STATUS,
    REAL_CANDIDATE,
)
from .actual_runner_assets import ActualRunnerAssetConfig, verify_base_model_asset
from .helper_component_guard import verify_helper_component_use_guard
from .helper_sdk_bridge import HelperSdkBridge
from .human_approval_sealed import evaluate_human_approval_sealed
from .local_sealed_runner import RealRunner, run_actual_runner_smoke
from .real_metrics import compute_claim_metrics, estimate_format_compliance, estimate_style_compliance, metric_fail_class

def _status_from_gate(
    *,
    base_status: str,
    helper_fail: str | None,
    parse_fail: str | None,
    runner_ok: bool,
    runner_fail: str | None,
    bridge_fail: str | None,
    metrics,
    fixed_eval_pass: bool,
    approval_allowed: bool,
    approval_fail: str | None,
    test_only_runner: bool,
) -> tuple[str, bool, str | None, bool]:
    if base_status in {PARTIAL_REAL_ASSET_VOLUME_MISSING, PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE} and not test_only_runner:
        return base_status, False, base_status, True
    if helper_fail:
        return helper_fail if str(helper_fail).startswith("PARTIAL_") else BLOCKED, False, helper_fail, True
    if parse_fail:
        return parse_fail if str(parse_fail).startswith("PARTIAL_") else BLOCKED, False, parse_fail, True
    if not runner_ok:
        if runner_fail in {PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE, PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED}:
            return runner_fail, False, runner_fail, True
        return BLOCKED if str(runner_fail or "").startswith("BLOCK_") else ASSET_INVENTORY_PASS, False, runner_fail, True
    if test_only_runner:
        return REAL_CANDIDATE, False, "TEST_ONLY_RUNNER_NOT_REAL_APPROVAL", True
    if bridge_fail:
        if bridge_fail in {PARTIAL_HELPER_SDK_UNAVAILABLE, PARTIAL_EMBEDDER_UNAVAILABLE, PARTIAL_BGE_M3_FALLBACK_USED}:
            return REAL_CANDIDATE, False, bridge_fail, True
        return BLOCKED, False, bridge_fail, True
    metric_fail = metric_fail_class(metrics)
    if metric_fail:
        return BLOCKED if metric_fail.startswith("BLOCK_") else REAL_CANDIDATE, False, metric_fail, True
    if not fixed_eval_pass:
        return REAL_CANDIDATE, False, FIXED_EVAL_PENDING, True
    if not approval_allowed:
        return REAL_CANDIDATE if approval_fail == "BLOCK_HUMAN_APPROVAL_MISSING" else BLOCKED, False, approval_fail, True
    return PASS_STATUS, True, None, False

def run_box3_actual_operation(
    envelope: Box3ActualRuntimeEnvelope,
    *,
    base_config: ActualRunnerAssetConfig | None = None,
    helper_component_guard: dict[str, Any] | None = None,
    human_approval_config: dict[str, Any] | None = None,
    fixed_eval_pass: bool = False,
    runner: RealRunner | None = None,
    sdk_bridge: HelperSdkBridge | None = None,
) -> Box3ActualOperationVerdict:
    stage_trace: list[dict[str, Any]] = []
    if not envelope.policy_gate_allowed:
        return Box3ActualOperationVerdict(
            schema_version="box3.actual_operation.v1_2",
            request_id=envelope.request_id,
            request_digest=envelope.request_digest,
            status=BLOCKED,
            draft_text=None,
            draft_digest=None,
            metrics={},
            citations=[],
            stage_trace=[{"stage": "policy_gate", "passed": False, "fail_class": BLOCK_POLICY_GATE}],
            fail_class=BLOCK_POLICY_GATE,
            real_claim_allowed=False,
            human_approval_required=True,
            runner_measurements={},
            asset_measurements={},
            helper_sdk_receipts={},
        )

    base = verify_base_model_asset(base_config)
    stage_trace.append({"stage": "base_model_asset", "passed": base.allowed, "status": base.status, "fail_class": base.fail_class})

    helper = verify_helper_component_use_guard(helper_component_guard)
    stage_trace.append({"stage": "role_wiring", "passed": helper.allowed, "fail_class": helper.fail_class, "sdk_call_supported": helper.sdk_call_supported, "helper_stack_supported": helper.helper_stack_supported})

    bridge = sdk_bridge or HelperSdkBridge.from_env()
    evidence_bundle = bridge.parse_evidence(envelope.reference_text_runtime_only)
    envelope_evidence_count = len(evidence_bundle.evidence_units_runtime)
    stage_trace.append({
        "stage": "helper7_parse_evidence",
        "passed": evidence_bundle.parse_success,
        "fail_class": evidence_bundle.fail_class,
        "evidence_count": envelope_evidence_count,
    })

    if base.allowed and helper.allowed and evidence_bundle.parse_success:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config, helper_guard=helper_component_guard)
    else:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config, helper_guard=helper_component_guard) if runner is not None else None
    if smoke is None:
        runner_ok = False
        runner_fail = base.fail_class or helper.fail_class or evidence_bundle.fail_class
        runner_measurements = {}
        draft = ""
        test_only = False
    else:
        runner_ok = smoke.ok
        runner_fail = smoke.fail_class
        runner_measurements = smoke.to_dict()
        draft = smoke.draft_text or ""
        test_only = smoke.test_only_runner
    stage_trace.append({"stage": "draft_runner_helper3_helper5_stack", "passed": runner_ok, "fail_class": runner_fail, **runner_measurements})

    grounding_bundle = bridge.ground_claims(draft, evidence_bundle) if draft else None
    if grounding_bundle is None:
        verdicts = []
        bridge_fail = runner_fail or evidence_bundle.fail_class
        citations = []
        metrics = compute_claim_metrics([], format_compliance=0.0, style_compliance=0.0, evidence_units=evidence_bundle.evidence_units_runtime)
        grounding_receipt = None
    else:
        verdicts = grounding_bundle.claim_verdicts
        bridge_fail = grounding_bundle.fail_class
        citations = [unit.citation() for unit in evidence_bundle.evidence_units_runtime]
        styled = bridge.apply_company_style(draft)
        if styled.style_applied:
            draft = styled.draft_text_runtime
        if styled.fail_class and bridge_fail is None:
            bridge_fail = styled.fail_class
        format_score = estimate_format_compliance(draft)
        style_score = estimate_style_compliance(draft)
        metrics = compute_claim_metrics(verdicts, format_compliance=format_score, style_compliance=style_score, evidence_units=evidence_bundle.evidence_units_runtime)
        grounding_receipt = grounding_bundle.persistable_dict()
        stage_trace.append({"stage": "helper4_grounding", "passed": grounding_bundle.summary.unsupported_claim_count == 0, "fail_class": grounding_bundle.fail_class, "embedder_provider": grounding_bundle.embedder_provider})
        stage_trace.append({"stage": "helper8_company_style", "passed": styled.style_applied, "fail_class": styled.fail_class})

    approval = evaluate_human_approval_sealed(human_approval_config, expected_scope_digest=envelope.request_digest)
    stage_trace.append({"stage": "human_approval", "passed": approval.allowed, "fail_class": approval.fail_class, "config_digest": approval.config_digest})

    status, real_allowed, fail_class, approval_required = _status_from_gate(
        base_status=base.status,
        helper_fail=helper.fail_class,
        parse_fail=evidence_bundle.fail_class,
        runner_ok=runner_ok,
        runner_fail=runner_fail,
        bridge_fail=bridge_fail,
        metrics=metrics,
        fixed_eval_pass=fixed_eval_pass,
        approval_allowed=approval.allowed,
        approval_fail=approval.fail_class,
        test_only_runner=test_only,
    )
    draft_text = draft if status in {REAL_CANDIDATE, PASS_STATUS} else None
    helper_receipts = {
        "evidence": evidence_bundle.persistable_dict(),
        "grounding": grounding_receipt,
    }
    return Box3ActualOperationVerdict(
        schema_version="box3.actual_operation.v1_2",
        request_id=envelope.request_id,
        request_digest=envelope.request_digest,
        status=status,  # type: ignore[arg-type]
        draft_text=draft_text,
        draft_digest=sha256_text(draft) if draft_text else None,
        metrics=metrics.to_dict(),
        citations=citations,
        stage_trace=stage_trace + [{"stage": "final_gate", "status": status, "real_claim_allowed": real_allowed, "fail_class": fail_class}],
        fail_class=fail_class,
        real_claim_allowed=real_allowed,
        human_approval_required=approval_required,
        runner_measurements=runner_measurements,
        asset_measurements={"base": base.to_dict(), "helper": helper.to_dict()},
        helper_sdk_receipts=helper_receipts,
    )
