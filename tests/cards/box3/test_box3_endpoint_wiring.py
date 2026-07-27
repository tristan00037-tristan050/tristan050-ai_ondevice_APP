from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from butler_pc_core.cards.box3.actual_contracts import sha256_text
from butler_pc_core.cards.box3.endpoint_wiring import run_box3_endpoint_wiring
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.local_sealed_runner import build_deterministic_test_runner
from butler_pc_core.cards.box3.model_identity import (
    hash_model_file_for_security,
)


REFERENCE = "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."
REQUEST = "납품 일정을 반영해 보고서 초안을 작성하세요."


@pytest.fixture()
def box3_model_digest(tmp_path, monkeypatch) -> str:
    """승인 배선 시험에 사용할 명시적 테스트 모델 identity를 제공한다."""
    model = tmp_path / "butler-1.7b-v9-2-r2b-q4_k_m.gguf"
    model.write_bytes(b"BOX3-MODEL-BYTES" * 512)
    identity = hash_model_file_for_security(str(model))
    monkeypatch.setattr(
        "butler_pc_core.cards.box3.endpoint_wiring.get_box3_model_identity_for_approval",
        lambda _path=None: identity,
    )
    return identity.model_digest


def _model_approval(scope_digest: str, *, allow: bool = True) -> dict:
    return {
        "schema_version": "box3.human_approval.v1",
        "approval_mode": "model_scope",
        "allow": allow,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("admin"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def _request_scope_approval(scope_digest: str) -> dict:
    approval = _model_approval(scope_digest)
    approval["approval_mode"] = "request_scope"
    return approval


def test_missing_approval_returns_contract_only_and_does_not_call_runner(box3_model_digest):
    called = {"value": False}

    def runner(_envelope):
        called["value"] = True
        raise AssertionError("runner must not be called before sealed approval")

    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=None,
        runner=runner,
    )

    assert response["status"] == "contract_only"
    assert response["actual_wiring"]["actual_status"] == "CONTRACT_ONLY"
    assert response["real_claim_allowed"] is False
    assert response["contract_only"] is True
    assert response["actual_wiring"]["approval_pre_gate_passed"] is False
    assert response["actual_wiring"]["runner_injected"] is False
    assert called["value"] is False


def test_desktop_rejects_request_scope(box3_model_digest):
    """desktop context 에서 request_scope 승인은 APP_MODEL_SCOPE_REQUIRED 로 차단."""
    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=_request_scope_approval(box3_model_digest),
        helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )
    assert response["status"] == "contract_only"
    assert response["fail_class"] == "APP_MODEL_SCOPE_REQUIRED"
    assert response["actual_wiring"]["runner_injected"] is False


def test_scope_mismatch_is_contract_only_and_runner_is_not_injected(box3_model_digest):
    wrong_scope_approval = _model_approval("sha256:" + "0" * 64)
    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=wrong_scope_approval,
        runner=build_deterministic_test_runner(),
    )
    assert response["status"] == "contract_only"
    assert response["actual_wiring"]["actual_status"] == "CONTRACT_ONLY"
    assert response["real_claim_allowed"] is False
    assert response["fail_class"] == "BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH"
    assert response["actual_wiring"]["runner_injected"] is False


def test_valid_approval_but_helper_guard_missing_never_injects_runner(box3_model_digest):
    called = {"value": False}

    def runner(_envelope):
        called["value"] = True
        return "제목: 실행되면 안 됩니다."

    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=_model_approval(box3_model_digest),
        helper_component_guard=None,
        fixed_eval_pass=True,
        runner=runner,
    )

    assert response["actual_wiring"]["approval_pre_gate_passed"] is True
    assert response["actual_wiring"]["runner_injected"] is False
    assert called["value"] is False
    assert response["real_claim_allowed"] is False


def test_valid_approval_and_helper_guard_allows_test_runner_candidate_only(box3_model_digest):
    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=_model_approval(box3_model_digest),
        helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )

    assert response["actual_wiring"]["approval_pre_gate_passed"] is True
    assert response["actual_wiring"]["runner_injected"] is True
    assert response["status"] in {"real_candidate", "blocked"}
    assert response["actual_wiring"]["actual_status"] in {"REAL_CANDIDATE", "BLOCKED"}
    assert response["real_claim_allowed"] is False
    assert response["external_send_zero"] is True
    assert response["raw_saved_zero"] is True


def test_response_is_digest_only_except_runtime_draft_text(box3_model_digest):
    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request=REQUEST,
        approval_config=_model_approval(box3_model_digest),
        helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )
    persisted = {k: v for k, v in response.items() if k not in {"draft_text", "actual_operation"}}
    encoded = str(persisted)
    assert REFERENCE not in encoded
    assert REQUEST not in encoded
    assert ("/" + "Users/") not in encoded
    assert ("/" + "Volumes/") not in encoded
