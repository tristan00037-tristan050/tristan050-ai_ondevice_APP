from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from butler_pc_core.cards.box3.endpoint_wiring import run_box3_endpoint_wiring
from butler_pc_core.cards.box3.human_approval_sealed import (
    APPROVAL_CONTEXT_DESKTOP_APP,
    APPROVAL_CONTEXT_EVAL_PIPELINE,
    APPROVAL_MODE_MODEL,
    ApprovalScopeError,
    HumanApprovalSealedVerdict,
    canonical_sha256_digest,
    display_sha256_digest,
    evaluate_human_approval_sealed,
    resolve_expected_scope_digest,
)
from butler_pc_core.cards.box3.model_identity import Box3ModelIdentity

MODEL_DIGEST = "sha256:" + "a" * 64
DEVICE_DIGEST = "sha256:" + "b" * 64
REQUEST_DIGEST = "sha256:" + "c" * 64
APPROVER_DIGEST = "sha256:" + "d" * 64


def _future_z(days: int = 10) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _approval(**updates):
    data = {
        "schema_version": "box3.human_approval.v2",
        "approval_mode": "model_scope",
        "approval_scope_kind": "box3_model_scope.v1",
        "approved_model_role": "box3_draft",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": APPROVER_DIGEST,
        "device_id_digest": DEVICE_DIGEST,
        "approval_scope_digest": MODEL_DIGEST,
        "approved_at": "2026-07-08T00:00:00Z",
        "expires_at": _future_z(),
        "status": "APPROVED_BOX3_MODEL_SCOPE",
    }
    data.update(updates)
    return data


def test_canonical_digest_accepts_prefix_and_bare_lowercase():
    assert canonical_sha256_digest(MODEL_DIGEST) == "a" * 64
    assert canonical_sha256_digest("A" * 64) == "a" * 64
    assert display_sha256_digest("A" * 64, prefix=True) == MODEL_DIGEST


def test_desktop_app_requires_model_scope_mode():
    with pytest.raises(ApprovalScopeError, match="APPROVAL_MODE_REQUIRED"):
        resolve_expected_scope_digest(
            {"approval_mode": "request_scope"},
            request_digest=REQUEST_DIGEST,
            model_digest=MODEL_DIGEST,
            context=APPROVAL_CONTEXT_DESKTOP_APP,
            runtime_device_digest=DEVICE_DIGEST,
        )


def test_desktop_app_requires_device_digest_present_in_file():
    data = _approval()
    data.pop("device_id_digest")
    with pytest.raises(ApprovalScopeError, match="APPROVAL_SCHEMA_INVALID|APPROVAL_DEVICE_MISSING"):
        resolve_expected_scope_digest(
            data,
            request_digest=REQUEST_DIGEST,
            model_digest=MODEL_DIGEST,
            context=APPROVAL_CONTEXT_DESKTOP_APP,
            runtime_device_digest=DEVICE_DIGEST,
        )


def test_desktop_app_blocks_copied_approval_on_other_device():
    with pytest.raises(ApprovalScopeError, match="APPROVAL_DEVICE_MISMATCH"):
        resolve_expected_scope_digest(
            _approval(device_id_digest="sha256:" + "e" * 64),
            request_digest=REQUEST_DIGEST,
            model_digest=MODEL_DIGEST,
            context=APPROVAL_CONTEXT_DESKTOP_APP,
            runtime_device_digest=DEVICE_DIGEST,
        )


def test_eval_pipeline_rejects_model_scope_injection():
    with pytest.raises(ApprovalScopeError, match="APPROVAL_MODE_INVALID"):
        resolve_expected_scope_digest(
            _approval(),
            request_digest=REQUEST_DIGEST,
            model_digest=MODEL_DIGEST,
            context=APPROVAL_CONTEXT_EVAL_PIPELINE,
            runtime_device_digest=DEVICE_DIGEST,
        )


def test_valid_model_scope_approval_allows_matching_model_and_device():
    expected, mode = resolve_expected_scope_digest(
        _approval(),
        request_digest=REQUEST_DIGEST,
        model_digest=MODEL_DIGEST,
        context=APPROVAL_CONTEXT_DESKTOP_APP,
        runtime_device_digest=DEVICE_DIGEST,
    )
    verdict = evaluate_human_approval_sealed(_approval(), expected_scope_digest=expected, mode=mode)
    assert verdict.allowed is True
    assert verdict.mode == APPROVAL_MODE_MODEL
    assert verdict.to_dict()["model_digest_status"] == "matched"


def test_scope_mismatch_when_model_changes():
    expected, mode = resolve_expected_scope_digest(
        _approval(),
        request_digest=REQUEST_DIGEST,
        model_digest="sha256:" + "f" * 64,
        context=APPROVAL_CONTEXT_DESKTOP_APP,
        runtime_device_digest=DEVICE_DIGEST,
    )
    verdict = evaluate_human_approval_sealed(_approval(), expected_scope_digest=expected, mode=mode)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH"


def test_endpoint_blocks_missing_model_scope_approval_before_runner():
    response = run_box3_endpoint_wiring(
        reference_docs=["참고 문서"],
        drafting_request="초안 작성",
        approval_config=None,
        model_identity=Box3ModelIdentity("box3_draft", MODEL_DIGEST, 100, 1, "cache"),
        runtime_device_digest=DEVICE_DIGEST,
    )
    assert response["status"] == "contract_only"
    assert response["fail_class"] == "APPROVAL_MODE_REQUIRED"
    assert response["actual_wiring"]["approval_mode"] == "model_scope"


def test_verdict_blocked_carries_mode():
    verdict = HumanApprovalSealedVerdict.blocked(fail_class="APPROVAL_DEVICE_MISMATCH", mode="model_scope")
    assert verdict.to_dict()["mode"] == "model_scope"
