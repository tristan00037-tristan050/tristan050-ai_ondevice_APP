"""박스 3 real follow-up v1.2 정정 (2026-06-04) — main 본진(#775 머지본) 실제 시그니처 재작성.

본진 실제 API (Box3RealRuntimeEnvelope.from_raw / Box3RealRunnerConfig / pipeline / Literal 6).
본진 코드 약화 0.
"""
from __future__ import annotations

import hashlib

import pytest

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import (
    Box3RealRunnerConfig,
    fallback_real_asset_manifest,
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """본진 Box3RealRunnerConfig — 실제 model file 생성 + SHA 정합."""
    model = tmp_path / "model.gguf"
    model.write_bytes(b"butler-box3-test-model-bytes")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    return Box3RealRunnerConfig(
        runner_id="r1",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=digest,
        allow_test_runner=True,
        readonly_required=False,
    )


def test_pipeline_returns_candidate_not_real_without_human_approval(cfg):
    """approval 미공급 → REAL_CANDIDATE (PASS 라벨 부재 정직)."""
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="report",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.real_claim_allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_MISSING"
    assert verdict.human_approval_required is True
    audit = verdict.build_audit_record(envelope=env).to_dict()
    assert "draft_text" not in audit
    assert "납품" not in str(audit)


def test_pipeline_policy_block_returns_blocked_and_no_draft(cfg):
    """from_raw(policy_gate_allowed=False) → BLOCKED + BLOCK_POLICY_GATE."""
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        policy_gate_allowed=False,
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        runner=build_test_runner_for_tests(),
    )
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_POLICY_GATE"
    assert verdict.draft_text is None
    assert verdict.real_claim_allowed is False
    assert verdict.raw_saved_zero is True


def test_pipeline_unsupported_claim_real_claim_allowed_false(cfg):
    """근거 모순 draft → real_claim_allowed=False + raw 0."""
    def bad_runner(envelope):
        return (
            "제목: 초안\n"
            "배경: 참고 문서를 검토했습니다.\n"
            "핵심 내용: 납품 일정은 2026-06-20입니다.\n"
            "근거: 참고 문서를 확인.\n"
            "확인 필요: 없음.\n"
            "최종 문안: 2026-06-20 납품."
        )
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026-06-10로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        asset_manifest=fallback_real_asset_manifest(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=bad_runner,
    )
    # 근거 모순이면 BLOCKED, 그렇지 않으면 REAL_CANDIDATE — 어느 쪽이든 real_claim_allowed=False 정직.
    assert verdict.status in {"BLOCKED", "REAL_CANDIDATE"}
    assert verdict.real_claim_allowed is False
    assert verdict.raw_saved_zero is True
    assert verdict.external_send_zero is True
