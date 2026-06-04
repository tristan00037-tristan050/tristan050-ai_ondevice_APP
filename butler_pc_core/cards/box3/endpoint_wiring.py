from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from .actual_contracts import (
    Box3ActualRuntimeEnvelope,
    assert_persistable_digest_only,
    sha256_text,
    stable_json_digest,
)
from .actual_fail_class import CONTRACT_ONLY
from .actual_operation_pipeline import run_box3_actual_operation
from .actual_runner_assets import ActualRunnerAssetConfig
from .helper_component_guard import verify_helper_component_use_guard
from .human_approval_sealed import (
    default_locked_human_approval,
    evaluate_human_approval_sealed,
    load_human_approval_config,
)
from .local_sealed_runner import RealRunner

DEFAULT_APPROVAL_PATH = Path.home() / ".butler" / "box3" / "human_approval_v1.json"
APPROVAL_PATH_ENV = "BUTLER_BOX3_HUMAN_APPROVAL_CONFIG_PATH"
HELPER_GUARD_PATH_ENV = "BUTLER_BOX3_HELPER_COMPONENT_GUARD_PATH"

# PR #778 정정: 본진 /v1/cards/3/draft legacy contract 보존 — response.status 는 소문자
# PipelineStatus (`contract_only`/`real_candidate`/`real`/`blocked`/`needs_review`).
# 신규 actual_operation SSOT 6 라벨 (대문자) 은 response.actual_operation.status 안에 보존
# (두 SSOT 공존, 봉합 0).
_LEGACY_STATUS_MAP: dict[str, str] = {
    "CONTRACT_ONLY": "contract_only",
    "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE": "contract_only",
    "ASSET_INVENTORY_PASS": "real_candidate",
    "REAL_CANDIDATE": "real_candidate",
    "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL": "real",
    "BLOCKED": "blocked",
}


def _to_legacy_status(actual_status: str | None) -> str:
    if not actual_status:
        return "contract_only"
    return _LEGACY_STATUS_MAP.get(actual_status, "contract_only")
FIXED_EVAL_REPORT_PATH_ENV = "BUTLER_BOX3_FIXED_EVAL_REPORT_PATH"


class Box3EndpointWiringError(RuntimeError):
    """Endpoint-wiring only error. Message is a fail_class/reason code, never raw input."""


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_server_local_sealed_approval(path: Path | None = None) -> dict[str, Any] | None:
    """Load sealed approval from server-local path only.

    Request body, UI flag, query parameter, or environment variable values are never
    interpreted as approval themselves. The environment variable can only point to
    a server-local JSON file.
    """
    selected = path or Path(os.environ.get(APPROVAL_PATH_ENV, str(DEFAULT_APPROVAL_PATH)))
    return load_human_approval_config(selected) if selected.exists() else None


def load_helper_component_guard(path: Path | None = None) -> dict[str, Any] | None:
    selected_raw = str(path) if path else os.environ.get(HELPER_GUARD_PATH_ENV)
    if not selected_raw:
        return None
    return _read_json_file(Path(selected_raw))


def load_fixed_eval_pass(path: Path | None = None) -> bool:
    """Return fixed-eval gate from a server-local verdict-only report.

    The endpoint does not accept fixed_eval_pass from the request body.
    Expected report shape examples:
      {"fixed_eval_pass": true}
      {"status": "FIXED_EVAL_PASS", "failed_count": 0, "case_count": 40}
    """
    selected_raw = str(path) if path else os.environ.get(FIXED_EVAL_REPORT_PATH_ENV)
    if not selected_raw:
        return False
    report = _read_json_file(Path(selected_raw))
    if not report:
        return False
    if report.get("fixed_eval_pass") is True:
        return True
    return (
        report.get("status") == "FIXED_EVAL_PASS"
        and int(report.get("case_count", 0)) >= 40
        and int(report.get("failed_count", 1)) == 0
    )


def _contract_only_actual_response(
    envelope: Box3ActualRuntimeEnvelope,
    *,
    fail_class: str | None,
    approval_digest: str | None,
    approval_allowed: bool,
    approval_fail_class: str | None,
) -> dict[str, Any]:
    response = {
        "schema_version": "box3.draft.response.v1_2",
        # PR #778 정정: legacy contract — status 는 소문자 PipelineStatus.
        "status": _to_legacy_status(CONTRACT_ONLY),
        "draft_text": None,
        "draft_digest": None,
        "citations": [],
        "metrics": {},
        "stage_trace": [
            {
                "stage": "approval_pre_gate",
                "passed": bool(approval_allowed),
                "fail_class": approval_fail_class,
                "runner_injected": False,
            }
        ],
        "fail_class": fail_class,
        "needs_review": True,
        "human_approval_required": True,
        "real_claim_allowed": False,
        "contract_only": True,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_text_logged": False,
        "request_digest": envelope.request_digest,
        # PR #778 정정: legacy /v1/cards/3/draft response 필드 보존 — audit 키 (digest-only).
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


def normalize_actual_verdict_to_legacy_response(
    result: Any,
    *,
    envelope: Box3ActualRuntimeEnvelope,
    approval_config_digest: str | None,
    runner_injected: bool,
) -> dict[str, Any]:
    """Preserve /v1/cards/3/draft response shape while adding actual-operation fields.

    draft_text is allowed only in the HTTP response. Persisted/evidence payloads must
    use to_persistable_dict or audit records, not this response body.
    """
    raw = result.to_response_dict() if hasattr(result, "to_response_dict") else dict(result)
    actual_status = raw.get("status")
    response = {
        "schema_version": "box3.draft.response.v1_2",
        # PR #778 정정: legacy contract — status 는 소문자 PipelineStatus.
        "status": _to_legacy_status(actual_status),
        "draft_text": raw.get("draft_text"),
        "draft_digest": raw.get("draft_digest"),
        "citations": raw.get("citations", []),
        "metrics": raw.get("metrics", {}),
        "stage_trace": raw.get("stage_trace", []),
        "fail_class": raw.get("fail_class"),
        "needs_review": (
            raw.get("status") in {"CONTRACT_ONLY", "REAL_CANDIDATE", "BLOCKED"}
            and raw.get("real_claim_allowed") is not True
        ),
        "human_approval_required": raw.get("human_approval_required", True),
        "real_claim_allowed": raw.get("real_claim_allowed") is True,
        "contract_only": raw.get("real_claim_allowed") is not True,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_text_logged": False,
        "request_digest": envelope.request_digest,
        # PR #778 정정: legacy /v1/cards/3/draft response 필드 보존 — audit 키 (digest-only).
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


def _build_envelope(
    *,
    reference_docs: list[str],
    drafting_request: str,
    format_hint: str,
    max_new_tokens: int,
    policy_gate_allowed: bool,
    request_id: str | None = None,
) -> Box3ActualRuntimeEnvelope:
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=reference_docs,
        drafting_request=drafting_request,
        format_hint=format_hint,
        max_new_tokens=max_new_tokens,
        request_id=request_id,
        policy_gate_allowed=policy_gate_allowed,
    )


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
    """Wire the existing Box 3 endpoint to actual-operation runner conditionally.

    Pre-gate order:
      1. Build runtime-only envelope.
      2. Load/evaluate server-local sealed approval against envelope.request_digest.
      3. If approval is not valid, return contract-only compatible response.
      4. Only after approval passes, allow actual operation pipeline to build/use a runner.
    """
    if not reference_docs or not drafting_request:
        raise Box3EndpointWiringError("BOX3_REAL_CONTRACT_INPUT_MISSING")

    envelope = _build_envelope(
        reference_docs=list(reference_docs),
        drafting_request=drafting_request,
        format_hint=format_hint,
        max_new_tokens=max_new_tokens,
        policy_gate_allowed=policy_gate_allowed,
        request_id=request_id,
    )

    selected_approval = approval_config if approval_config is not None else load_server_local_sealed_approval()
    if selected_approval is None:
        selected_approval = default_locked_human_approval(envelope.request_digest)
    approval = evaluate_human_approval_sealed(
        selected_approval,
        expected_scope_digest=envelope.request_digest,
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

    # Never inject a provided runner when helper component use is not allowed.
    # This closes the actual_operation_pipeline escape path where an explicit
    # runner could otherwise execute despite helper guard failure.
    runner_for_pipeline = runner if helper_guard_verdict.allowed else None

    result = run_box3_actual_operation(
        envelope,
        base_config=base_config,
        helper_component_guard=selected_guard,
        human_approval_config=selected_approval,
        fixed_eval_pass=load_fixed_eval_pass() if fixed_eval_pass is None else bool(fixed_eval_pass),
        runner=runner_for_pipeline,
    )
    return normalize_actual_verdict_to_legacy_response(
        result,
        envelope=envelope,
        approval_config_digest=approval.config_digest,
        runner_injected=runner_for_pipeline is not None,
    )


__all__ = [
    "APPROVAL_PATH_ENV",
    "DEFAULT_APPROVAL_PATH",
    "FIXED_EVAL_REPORT_PATH_ENV",
    "HELPER_GUARD_PATH_ENV",
    "Box3EndpointWiringError",
    "load_fixed_eval_pass",
    "load_helper_component_guard",
    "load_server_local_sealed_approval",
    "normalize_actual_verdict_to_legacy_response",
    "run_box3_endpoint_wiring",
]
