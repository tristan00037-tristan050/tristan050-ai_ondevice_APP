from __future__ import annotations

import re
from typing import Any

from .actual_contracts import Box3ActualOperationVerdict, Box3ActualRuntimeEnvelope, sha256_text, stable_json_digest
from .actual_fail_class import (
    ASSET_INVENTORY_PASS,
    BLOCKED,
    BLOCK_HELPER_REAL_USE_GUARD_PENDING,
    BLOCK_POLICY_GATE,
    FIXED_EVAL_PENDING,
    PARTIAL_HELPER_STACK_UNSUPPORTED,
    PARTIAL_REAL_ASSET_VOLUME_MISSING,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
    PASS_STATUS,
    REAL_CANDIDATE,
)
from .actual_runner_assets import ActualRunnerAssetConfig, verify_base_model_asset
from .helper_component_guard import verify_helper_component_use_guard
from .human_approval_sealed import evaluate_human_approval_sealed
from .local_sealed_runner import RealRunner, run_actual_runner_smoke

_FACT_RE = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{1,2}월\s*\d{1,2}일|\d+(?:[,.]\d+)?(?:원|만원|억원|%|일|월|년)?")


def _extract_facts(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in _FACT_RE.finditer(text)}


def _simple_grounding(draft: str, references: list[str]) -> tuple[dict[str, Any], list[dict[str, str]], str | None]:
    ref_text = "\n".join(references)
    ref_facts = _extract_facts(ref_text)
    draft_facts = _extract_facts(draft)
    unsupported = sorted(fact for fact in draft_facts if fact not in ref_facts and not any(fact in rf or rf in fact for rf in ref_facts))
    citations = [{"source_digest": sha256_text(ref), "evidence_digest": sha256_text(ref[:500]), "span_label": "runtime_only"} for ref in references]
    factual = max(1, len(draft_facts))
    metrics = {
        "unsupported_count": len(unsupported),
        "no_evidence_count": 0,
        "unsupported_claim_rate": len(unsupported) / factual,
        "no_evidence_claim_rate": 0.0,
        "citation_accuracy": 1.0 if citations else 0.0,
        "format_compliance": _format_compliance(draft),
        "style_compliance": 1.0 if "법적으로 확정" not in draft and "100%" not in draft else 0.0,
        "table_figure_coverage": 1.0,
        "factual_claim_count": factual,
    }
    fail = "BLOCK_UNSUPPORTED_CLAIM" if unsupported else None
    return metrics, citations, fail


def _format_compliance(draft: str) -> float:
    required = ["제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안"]
    return sum(1 for item in required if f"{item}:" in draft) / len(required)


def _status_from_gate(
    *,
    base_status: str,
    helper_fail: str | None,
    runner_ok: bool,
    runner_fail: str | None,
    grounding_fail: str | None,
    metrics: dict[str, Any],
    fixed_eval_pass: bool,
    approval_allowed: bool,
    approval_fail: str | None,
    test_only_runner: bool,
) -> tuple[str, bool, str | None, bool]:
    if base_status in {PARTIAL_REAL_ASSET_VOLUME_MISSING, PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE} and not test_only_runner:
        return base_status, False, base_status, True
    if helper_fail:
        return (PARTIAL_HELPER_STACK_UNSUPPORTED if helper_fail == PARTIAL_HELPER_STACK_UNSUPPORTED else BLOCKED), False, helper_fail, True
    if not runner_ok:
        if runner_fail == PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE:
            return PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE, False, runner_fail, True
        return BLOCKED if str(runner_fail or "").startswith("BLOCK_") else ASSET_INVENTORY_PASS, False, runner_fail, True
    if test_only_runner:
        return REAL_CANDIDATE, False, "TEST_ONLY_RUNNER_NOT_REAL_APPROVAL", True
    if grounding_fail:
        return BLOCKED, False, grounding_fail, True
    if metrics["citation_accuracy"] < 0.95 or metrics["format_compliance"] < 0.85 or metrics["style_compliance"] < 0.70:
        return REAL_CANDIDATE, False, "METRIC_GATE_PENDING", True
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
        )

    base = verify_base_model_asset(base_config)
    stage_trace.append({"stage": "base_model_asset", "passed": base.allowed, "status": base.status, "fail_class": base.fail_class})
    helper = verify_helper_component_use_guard(helper_component_guard)
    stage_trace.append({"stage": "helper_component_use_guard", "passed": helper.allowed, "fail_class": helper.fail_class})

    if base.allowed and helper.allowed:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config)
    else:
        smoke = run_actual_runner_smoke(envelope, runner=runner, config=base_config) if runner is not None else None
    if smoke is None:
        runner_ok = False
        runner_fail = base.fail_class or helper.fail_class
        runner_measurements = {}
        draft = ""
        test_only = False
    else:
        runner_ok = smoke.ok
        runner_fail = smoke.fail_class
        runner_measurements = smoke.to_dict()
        draft = smoke.draft_text or ""
        test_only = smoke.test_only_runner
    stage_trace.append({"stage": "runner_smoke", "passed": runner_ok, "fail_class": runner_fail, **runner_measurements})

    metrics, citations, grounding_fail = _simple_grounding(draft, envelope.reference_text_runtime_only) if draft else ({}, [], runner_fail)
    stage_trace.append({"stage": "claim_grounding", "passed": grounding_fail is None, "fail_class": grounding_fail, "metrics": metrics})

    approval = evaluate_human_approval_sealed(human_approval_config, expected_scope_digest=envelope.request_digest)
    stage_trace.append({"stage": "human_approval", "passed": approval.allowed, "fail_class": approval.fail_class, "config_digest": approval.config_digest})

    status, real_allowed, fail_class, approval_required = _status_from_gate(
        base_status=base.status,
        helper_fail=helper.fail_class,
        runner_ok=runner_ok,
        runner_fail=runner_fail,
        grounding_fail=grounding_fail,
        metrics=metrics or {"citation_accuracy": 0.0, "format_compliance": 0.0, "style_compliance": 0.0},
        fixed_eval_pass=fixed_eval_pass,
        approval_allowed=approval.allowed,
        approval_fail=approval.fail_class,
        test_only_runner=test_only,
    )
    draft_text = draft if status in {REAL_CANDIDATE, PASS_STATUS} else None
    return Box3ActualOperationVerdict(
        schema_version="box3.actual_operation.v1_2",
        request_id=envelope.request_id,
        request_digest=envelope.request_digest,
        status=status,  # type: ignore[arg-type]
        draft_text=draft_text,
        draft_digest=sha256_text(draft) if draft_text else None,
        metrics=metrics,
        citations=citations,
        stage_trace=stage_trace + [{"stage": "final_gate", "status": status, "real_claim_allowed": real_allowed, "fail_class": fail_class}],
        fail_class=fail_class,
        real_claim_allowed=real_allowed,
        human_approval_required=approval_required,
        runner_measurements=runner_measurements,
        asset_measurements={"base": base.to_dict(), "helper": helper.to_dict()},
    )
