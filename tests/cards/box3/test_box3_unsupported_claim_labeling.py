from __future__ import annotations

from datetime import datetime, timedelta, timezone

from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope, sha256_text
from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_DLP_OUTBOUND_DRAFT,
    BLOCK_HUMAN_APPROVAL_KILL_SWITCH,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.actual_operation_pipeline import (
    UNSUPPORTED_CLAIM_LABEL,
    annotate_unsupported_lines,
    run_box3_actual_operation,
)
from butler_pc_core.cards.box3.actual_runner_assets import ActualRunnerAssetConfig, BASE_MODEL_PATH_ENV
from butler_pc_core.cards.box3.endpoint_wiring import run_box3_endpoint_wiring
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.model_identity import hash_model_file_for_security


REFERENCE = "참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."


def _guard() -> dict:
    return build_example_component_use_guard(
        allow=True,
        stack_supported=True,
        sdk_call_supported=True,
        embedder_provider="helper2_sdk",
    )


def _approval(scope_digest: str) -> dict:
    return {
        "schema_version": "box3.human_approval.v1",
        "approval_mode": "model_scope",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("admin"),
        "approval_scope_digest": scope_digest,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }


def _write_model(tmp_path, monkeypatch) -> str:
    model = tmp_path / "butler-1.7b-v9-2-r2b-q4_k_m.gguf"
    model.write_bytes(b"BOX3-LABEL-DEMOTION-MODEL" * 256)
    monkeypatch.setenv(BASE_MODEL_PATH_ENV, str(model))
    return hash_model_file_for_security(str(model)).model_digest


def _unsupported_runner(_env) -> str:
    return (
        "제목: 납품 일정 보고\n"
        "배경: 납품 일정은 2026년 6월 10일입니다.\n"
        "핵심 내용: 납품 일정은 2026년 6월 20일입니다.\n"
        "근거: 참고 문서 기준으로 검토합니다.\n"
        "확인 필요: 담당자는 원문에 없으면 확정하지 않습니다.\n"
        "최종 문안: 납품 일정은 2026년 6월 20일 기준으로 검토합니다."
    )


def test_unsupported_claim_is_real_candidate_with_runtime_label(tmp_path, monkeypatch):
    _write_model(tmp_path, monkeypatch)
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=[REFERENCE],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
    )

    verdict = run_box3_actual_operation(
        env,
        base_config=ActualRunnerAssetConfig(allow_test_asset=True),
        helper_component_guard=_guard(),
        runner=_unsupported_runner,
    )

    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.fail_class == NEEDS_REVIEW_UNSUPPORTED_CLAIM
    assert verdict.needs_review is True
    assert verdict.unsupported_claim_count >= 1
    assert verdict.annotated_claim_count >= 1
    assert verdict.label_coverage_ok is True
    assert verdict.draft_text is not None
    assert UNSUPPORTED_CLAIM_LABEL in verdict.draft_text
    assert "2026년 6월 20일" in verdict.draft_text
    assert "2026년 6월 20일" not in str(verdict.to_persistable_dict())


def test_endpoint_exposes_label_metadata_and_real_candidate_status(tmp_path, monkeypatch):
    model_digest = _write_model(tmp_path, monkeypatch)

    response = run_box3_endpoint_wiring(
        reference_docs=[REFERENCE],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
        approval_config=_approval(model_digest),
        helper_component_guard=_guard(),
        fixed_eval_pass=True,
        base_config=ActualRunnerAssetConfig(allow_test_asset=True),
        runner=_unsupported_runner,
    )

    assert response["status"] == "real_candidate"
    assert response["needs_review"] is True
    assert response["review_reason_code"] == NEEDS_REVIEW_UNSUPPORTED_CLAIM
    assert response["unsupported_claim_count"] >= 1
    assert response["annotated_claim_count"] >= 1
    assert response["label_coverage_ok"] is True
    assert UNSUPPORTED_CLAIM_LABEL in response["draft_text"]


def test_label_matching_failure_labels_all_factual_lines_without_silent_pass():
    missing_digest = "sha256:" + "a" * 64
    draft = (
        "제목: 납품 보고\n"
        "핵심 내용: 납품 일정은 2026년 6월 20일입니다.\n"
        "최종 문안: 납품 일정은 2026년 6월 20일 기준입니다."
    )

    annotated, meta = annotate_unsupported_lines(draft, {missing_digest})

    assert meta["label_coverage_ok"] is False
    assert meta["review_reason_code"] == NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL
    assert annotated.startswith("[전체 검토 필요]")
    assert annotated.count(UNSUPPORTED_CLAIM_LABEL) >= 2


def test_outbound_dlp_guard_prevents_labeled_draft_output(tmp_path, monkeypatch):
    _write_model(tmp_path, monkeypatch)

    def leaking_runner(_env) -> str:
        return (
            "제목: 보안 메모\n"
            "배경: 보안 메모 검토 일정은 2026년 6월 10일입니다.\n"
            "핵심 내용: 보안 메모 검토 일정은 2026년 6월 10일입니다.\n"
            "근거: api_key: sk-test-secret-value-123456\n"
            "확인 필요: 담당자는 원문에 없으면 확정하지 않습니다.\n"
            "최종 문안: 보안 메모 검토 일정은 2026년 6월 10일입니다."
        )

    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 보안 메모 검토 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="보안 메모 초안을 작성하세요.",
    )
    verdict = run_box3_actual_operation(
        env,
        base_config=ActualRunnerAssetConfig(allow_test_asset=True),
        helper_component_guard=_guard(),
        runner=leaking_runner,
    )

    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == BLOCK_DLP_OUTBOUND_DRAFT
    assert verdict.draft_text is None


def test_hard_approval_failure_blocks_before_unsupported_review_candidate(tmp_path, monkeypatch):
    model_digest = _write_model(tmp_path, monkeypatch)
    approval = _approval(model_digest)
    approval["kill_switch_enabled"] = True
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=[REFERENCE],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
    )

    verdict = run_box3_actual_operation(
        env,
        base_config=ActualRunnerAssetConfig(allow_test_asset=True),
        helper_component_guard=_guard(),
        human_approval_config=approval,
        fixed_eval_pass=True,
        runner=_unsupported_runner,
    )

    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == BLOCK_HUMAN_APPROVAL_KILL_SWITCH
    assert verdict.draft_text is None


def test_hard_approval_failure_beats_unsupported_demotion_for_direct_callers():
    # P2-1(코덱스): run_box3_actual_operation 직접 호출(엔드포인트 pre-gate 우회) 시에도
    # kill-switch/revoked/expired/scope-mismatch 승인 실패는 unsupported 강등(REAL_CANDIDATE)
    # 보다 우선해 BLOCKED 여야 한다. 승인 우선순위 게이트가 bridge_fail 강등 분기보다 앞선다.
    from butler_pc_core.cards.box3.actual_fail_class import BLOCKED

    for approval_fail in (
        "BLOCK_HUMAN_APPROVAL_KILL_SWITCH",
        "BLOCK_HUMAN_APPROVAL_REVOKED",
        "BLOCK_HUMAN_APPROVAL_EXPIRED",
        "BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH",
    ):
        status, real_allowed, fail_class, _ = _gate(
            bridge_fail=NEEDS_REVIEW_UNSUPPORTED_CLAIM,
            approval_allowed=False,
            approval_fail=approval_fail,
        )
        assert status == BLOCKED, approval_fail
        assert real_allowed is False, approval_fail
        assert fail_class == approval_fail
    # MISSING 은 설계상 검토후보(REAL_CANDIDATE)로 남는다 — 보안 차단이 아니라 미설정 상태.
    status_missing, _, _, _ = _gate(
        bridge_fail=NEEDS_REVIEW_UNSUPPORTED_CLAIM,
        approval_allowed=False,
        approval_fail="BLOCK_HUMAN_APPROVAL_MISSING",
    )
    assert status_missing == "REAL_CANDIDATE"


def test_known_needs_review_fail_classes_are_not_blocking():
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_UNSUPPORTED_CLAIM) is False
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL) is False
    assert is_blocking_actual_fail_class("UNKNOWN_NEW_FAIL_CLASS") is True


def test_unregistered_runner_fail_is_conservatively_blocked():
    # P1-1: severity map 에 없고 BLOCK_ 접두도 아닌 runner_fail 도 보수적으로 BLOCKED 되어야 한다
    # (runner 실패 경로가 prefix-only 체크에서 조용히 ASSET_INVENTORY_PASS 로 통과하던 잔존 결함).
    from butler_pc_core.cards.box3.actual_fail_class import BLOCKED
    from butler_pc_core.cards.box3.actual_operation_pipeline import _status_from_gate

    status, real_allowed, fail_class, _ = _status_from_gate(
        base_status="ASSET_INVENTORY_PASS",
        helper_fail=None,
        parse_fail=None,
        runner_ok=False,
        runner_fail="UNREGISTERED_RUNNER_FAIL_XYZ",
        bridge_fail=None,
        metrics=None,
        fixed_eval_pass=False,
        approval_allowed=False,
        approval_fail=None,
        test_only_runner=False,
    )
    assert status == BLOCKED
    assert real_allowed is False
    assert fail_class == "UNREGISTERED_RUNNER_FAIL_XYZ"


def _gate(**overrides):
    from butler_pc_core.cards.box3.actual_operation_pipeline import _status_from_gate

    kwargs = dict(
        base_status="ASSET_INVENTORY_PASS",
        helper_fail=None,
        parse_fail=None,
        runner_ok=True,
        runner_fail=None,
        bridge_fail=None,
        metrics=None,
        fixed_eval_pass=True,
        approval_allowed=True,
        approval_fail=None,
        test_only_runner=False,
    )
    kwargs.update(overrides)
    return _status_from_gate(**kwargs)


def test_unregistered_helper_fail_is_conservatively_blocked():
    from butler_pc_core.cards.box3.actual_fail_class import BLOCKED

    status, real_allowed, fail_class, _ = _gate(helper_fail="UNREGISTERED_HELPER_FAIL_XYZ")
    assert status == BLOCKED
    assert real_allowed is False
    assert fail_class == "UNREGISTERED_HELPER_FAIL_XYZ"


def test_unregistered_parse_fail_is_conservatively_blocked():
    from butler_pc_core.cards.box3.actual_fail_class import BLOCKED

    status, real_allowed, fail_class, _ = _gate(parse_fail="UNREGISTERED_PARSE_FAIL_XYZ")
    assert status == BLOCKED
    assert real_allowed is False
    assert fail_class == "UNREGISTERED_PARSE_FAIL_XYZ"


def test_partial_helper_and_parse_fail_still_pass_through():
    # 회귀 방지: 등록된 PARTIAL_ 계열은 여전히 그 status 로 통과(하드블록 아님).
    status_h, _, fc_h, _ = _gate(helper_fail="PARTIAL_HELPER_STACK_UNSUPPORTED")
    assert status_h == "PARTIAL_HELPER_STACK_UNSUPPORTED" and fc_h == "PARTIAL_HELPER_STACK_UNSUPPORTED"
    status_p, _, fc_p, _ = _gate(parse_fail="PARTIAL_HELPER_SDK_UNAVAILABLE")
    assert status_p == "PARTIAL_HELPER_SDK_UNAVAILABLE" and fc_p == "PARTIAL_HELPER_SDK_UNAVAILABLE"
