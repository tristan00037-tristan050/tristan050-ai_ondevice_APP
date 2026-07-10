from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .actual_contracts import Box3ActualRuntimeEnvelope, assert_persistable_digest_only
from .actual_fail_class import CONTRACT_ONLY, Box3ApprovalError
from .actual_operation_pipeline import run_box3_actual_operation
from .actual_runner_assets import ActualRunnerAssetConfig
from .helper_component_guard import verify_helper_component_use_guard
from .human_approval_sealed import (
    APPROVAL_CONTEXT_DESKTOP_APP,
    default_locked_human_approval,
    evaluate_human_approval_sealed,
    load_human_approval_config,
    resolve_expected_scope_digest,
)
from .model_identity import get_box3_model_identity_for_approval
from .local_sealed_runner import RealRunner

DEFAULT_APPROVAL_PATH = Path.home() / ".butler" / "box3" / "human_approval_v1.json"
APPROVAL_PATH_ENV = "BUTLER_BOX3_HUMAN_APPROVAL_CONFIG_PATH"
HELPER_GUARD_PATH_ENV = "BUTLER_BOX3_HELPER_COMPONENT_GUARD_PATH"
FIXED_EVAL_REPORT_PATH_ENV = "BUTLER_BOX3_FIXED_EVAL_REPORT_PATH"

_LEGACY_STATUS_MAP = {
    "CONTRACT_ONLY": "contract_only",
    "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE": "contract_only",
    "PARTIAL_REAL_ASSET_VOLUME_MISSING": "contract_only",
    "PARTIAL_HELPER_STACK_UNSUPPORTED": "contract_only",
    "PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED": "contract_only",
    "PARTIAL_HELPER_SDK_UNAVAILABLE": "contract_only",
    "PARTIAL_EMBEDDER_UNAVAILABLE": "contract_only",
    "PARTIAL_BGE_M3_FALLBACK_USED": "real_candidate",
    "ASSET_INVENTORY_PASS": "real_candidate",
    "REAL_CANDIDATE": "real_candidate",
    "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL": "real",
    "BLOCKED": "blocked",
}

class Box3EndpointWiringError(RuntimeError):
    """Endpoint-wiring only error. Message is a fail_class/reason code, never raw input."""

def _to_legacy_status(actual_status: str | None) -> str:
    if not actual_status:
        return "contract_only"
    return _LEGACY_STATUS_MAP.get(actual_status, "contract_only")


def _derive_terminal_stage(stage_trace: Any, fail_class: Any) -> str | None:
    """Return the actionable failure stage without exposing runtime text."""
    if not isinstance(fail_class, str) or not fail_class:
        return None
    if not isinstance(stage_trace, list):
        return None

    matching: list[str] = []
    fallback: list[str] = []
    for entry in stage_trace:
        if not isinstance(entry, dict):
            continue
        stage = entry.get("stage")
        if not isinstance(stage, str) or not stage:
            continue
        entry_fail = entry.get("fail_class")
        if entry_fail == fail_class:
            matching.append(stage)
        # fallback 은 순수하게 "실행이 실패로 표시된 단계"(passed is False)만 대상으로 한다.
        # matching 에서 이미 fail_class 일치를 걸렀으므로 entry_fail 단독 조건은 too broad.
        if entry.get("passed") is False:
            fallback.append(stage)

    for stage in reversed(matching):
        if stage != "final_gate":
            return stage
    if matching:
        return matching[-1]
    return fallback[-1] if fallback else None


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None

def load_server_local_sealed_approval(path: Path | None = None) -> dict[str, Any] | None:
    selected = path or Path(os.environ.get(APPROVAL_PATH_ENV, str(DEFAULT_APPROVAL_PATH)))
    return load_human_approval_config(selected) if selected.exists() else None

def load_helper_component_guard(path: Path | None = None) -> dict[str, Any] | None:
    selected_raw = str(path) if path else os.environ.get(HELPER_GUARD_PATH_ENV)
    if not selected_raw:
        return None
    return _read_json_file(Path(selected_raw))

def load_fixed_eval_pass(path: Path | None = None) -> bool:
    selected_raw = str(path) if path else os.environ.get(FIXED_EVAL_REPORT_PATH_ENV)
    if not selected_raw:
        return False
    report = _read_json_file(Path(selected_raw))
    if not report:
        return False
    if report.get("fixed_eval_pass") is True:
        return True
    return report.get("status") == "FIXED_EVAL_PASS" and int(report.get("case_count", 0)) >= 40 and int(report.get("failed_count", 1)) == 0

def _contract_only_actual_response(envelope: Box3ActualRuntimeEnvelope, *, fail_class: str | None, approval_digest: str | None, approval_allowed: bool, approval_fail_class: str | None) -> dict[str, Any]:
    stage_trace = [{"stage": "approval_pre_gate", "passed": bool(approval_allowed), "fail_class": approval_fail_class, "runner_injected": False}]
    response = {
        "schema_version": "box3.draft.response.v1_2",
        "status": _to_legacy_status(CONTRACT_ONLY),
        "draft_text": None,
        "draft_digest": None,
        "citations": [],
        "metrics": {},
        "stage_trace": stage_trace,
        "fail_class": fail_class,
        "terminal_stage": _derive_terminal_stage(stage_trace, fail_class) or "approval_pre_gate",
        "needs_review": True,
        "review_reason_code": fail_class,
        "unsupported_claim_count": 0,
        "annotated_claim_count": 0,
        "label_coverage_ok": True,
        "human_approval_required": True,
        "real_claim_allowed": False,
        "contract_only": True,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_text_logged": False,
        "request_digest": envelope.request_digest,
        "audit": {
            "schema_version": "box3.draft.audit.v1_2",
            "request_digest": envelope.request_digest,
            "external_send_zero": True,
            "raw_saved_zero": True,
            "raw_text_logged": False,
            "fail_class": fail_class,
            "approval_config_digest": approval_digest,
        },
        "actual_wiring": {
            "schema_version": "box3.endpoint_wiring.v1_2",
            "actual_status": CONTRACT_ONLY,
            "approval_pre_gate_passed": bool(approval_allowed),
            "approval_config_digest": approval_digest,
            "runner_injected": False,
            "request_flag_used_for_real": False,
            "ui_flag_used_for_real": False,
        },
    }
    assert_persistable_digest_only({k: v for k, v in response.items() if k != "draft_text"})
    return response

def normalize_actual_verdict_to_legacy_response(result: Any, *, envelope: Box3ActualRuntimeEnvelope, approval_config_digest: str | None, runner_injected: bool) -> dict[str, Any]:
    raw = result.to_response_dict() if hasattr(result, "to_response_dict") else dict(result)
    actual_status = raw.get("status")
    stage_trace = raw.get("stage_trace", [])
    fail_class = raw.get("fail_class")
    response = {
        "schema_version": "box3.draft.response.v1_2",
        "status": _to_legacy_status(actual_status),
        "draft_text": raw.get("draft_text"),
        "draft_digest": raw.get("draft_digest"),
        "citations": raw.get("citations", []),
        "metrics": raw.get("metrics", {}),
        "stage_trace": stage_trace,
        "fail_class": fail_class,
        "terminal_stage": _derive_terminal_stage(stage_trace, fail_class),
        "needs_review": raw.get("needs_review") is True or (raw.get("status") in {"CONTRACT_ONLY", "REAL_CANDIDATE", "BLOCKED"} and raw.get("real_claim_allowed") is not True),
        "review_reason_code": raw.get("review_reason_code") or raw.get("fail_class"),
        "unsupported_claim_count": int(raw.get("unsupported_claim_count") or 0),
        "annotated_claim_count": int(raw.get("annotated_claim_count") or 0),
        "label_coverage_ok": raw.get("label_coverage_ok") is not False,
        "human_approval_required": raw.get("human_approval_required", True),
        "real_claim_allowed": raw.get("real_claim_allowed") is True,
        "contract_only": raw.get("real_claim_allowed") is not True,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_text_logged": False,
        "request_digest": envelope.request_digest,
        "audit": {
            "schema_version": "box3.draft.audit.v1_2",
            "request_digest": envelope.request_digest,
            "external_send_zero": True,
            "raw_saved_zero": True,
            "raw_text_logged": False,
            "fail_class": raw.get("fail_class"),
            "approval_config_digest": approval_config_digest,
            "actual_status": actual_status,
        },
        "actual_operation": raw,
        "actual_wiring": {
            "schema_version": "box3.endpoint_wiring.v1_2",
            "actual_status": actual_status,
            "approval_pre_gate_passed": True,
            "approval_config_digest": approval_config_digest,
            "runner_injected": bool(runner_injected),
            "request_flag_used_for_real": False,
            "ui_flag_used_for_real": False,
        },
    }
    persist_probe = {k: v for k, v in response.items() if k not in {"draft_text", "actual_operation"}}
    assert_persistable_digest_only(persist_probe)
    return response

def run_box3_endpoint_wiring(
    *,
    reference_docs: list[str],
    drafting_request: str,
    format_hint: str = "자유형",
    max_new_tokens: int = 512,
    policy_gate_allowed: bool = True,
    request_id: str | None = None,
    approval_config: dict[str, Any] | None = None,
    helper_component_guard: dict[str, Any] | None = None,
    fixed_eval_pass: bool | None = None,
    base_config: ActualRunnerAssetConfig | None = None,
    runner: RealRunner | None = None,
) -> dict[str, Any]:
    if not reference_docs or not drafting_request:
        raise Box3EndpointWiringError("BOX3_REAL_CONTRACT_INPUT_MISSING")
    envelope = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=reference_docs,
        drafting_request=drafting_request,
        format_hint=format_hint,
        max_new_tokens=max_new_tokens,
        request_id=request_id,
        policy_gate_allowed=policy_gate_allowed,
    )
    selected_approval = approval_config if approval_config is not None else load_server_local_sealed_approval()
    if selected_approval is None:
        selected_approval = default_locked_human_approval(envelope.request_digest)

    # v1.2 §3.1/§3.4: desktop app 경로는 model_scope 만 허용한다(request_scope fallback 0).
    # 승인 전용 identity 를 매번 full rehash 하여 얻고, 그 model_digest 를 기대 scope 로 고정한다.
    model_identity = get_box3_model_identity_for_approval()
    try:
        expected_digest, approval_mode = resolve_expected_scope_digest(
            selected_approval,
            request_digest=envelope.request_digest,
            model_digest=model_identity.model_digest if model_identity else None,
            context=APPROVAL_CONTEXT_DESKTOP_APP,
        )
    except Box3ApprovalError as exc:
        # APP_MODEL_SCOPE_REQUIRED / MODEL_DIGEST_UNAVAILABLE 등 고정 reason 으로 contract_only 차단.
        return _contract_only_actual_response(
            envelope,
            fail_class=str(exc) or "BLOCK_HUMAN_APPROVAL_MISSING",
            approval_digest=None,
            approval_allowed=False,
            approval_fail_class=str(exc),
        )

    approval = evaluate_human_approval_sealed(
        selected_approval,
        expected_scope_digest=expected_digest,
        approval_mode=approval_mode,
        approval_context=APPROVAL_CONTEXT_DESKTOP_APP,
    )
    if not approval.allowed:
        return _contract_only_actual_response(
            envelope,
            fail_class=approval.fail_class or "BLOCK_HUMAN_APPROVAL_MISSING",
            approval_digest=approval.config_digest,
            approval_allowed=False,
            approval_fail_class=approval.fail_class,
        )
    selected_guard = helper_component_guard if helper_component_guard is not None else load_helper_component_guard()
    helper_guard_verdict = verify_helper_component_use_guard(selected_guard)
    runner_for_pipeline = runner if helper_guard_verdict.allowed else None
    result = run_box3_actual_operation(
        envelope,
        base_config=base_config,
        helper_component_guard=selected_guard,
        human_approval_config=selected_approval,
        fixed_eval_pass=load_fixed_eval_pass() if fixed_eval_pass is None else bool(fixed_eval_pass),
        runner=runner_for_pipeline,
        approval_expected_scope_digest=expected_digest,
        approval_mode=approval_mode,
        approval_context=APPROVAL_CONTEXT_DESKTOP_APP,
        approved_model_identity=model_identity,
    )
    return normalize_actual_verdict_to_legacy_response(result, envelope=envelope, approval_config_digest=approval.config_digest, runner_injected=runner_for_pipeline is not None)
