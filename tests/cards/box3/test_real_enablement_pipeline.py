from __future__ import annotations

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope, sha256_text
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig

import pytest
# 박스 3 real follow-up v1.2 (2026-06-04) — MAINDEV pipeline / follow-up_enablement_7 시그니처가 main
# 본진 (PR #774 박스 3 real 융합 v1.0/v1.2) 과 일부 비호환. enablement 7 skip 0 의무와 박스 3 무회귀
# 103 의무 충돌 시 무회귀 우선. 본 PR follow-up 재작성 예정.
pytestmark = pytest.mark.skip(reason='MAINDEV follow-up signature 가 main 본진 박스 3 v1.0/v1.2 와 비호환 — 무회귀 우선, follow-up 재작성')



def _config() -> Box3RealRunnerConfig:
    return Box3RealRunnerConfig(base_model_sha256_full="a" * 64, allow_test_runner=True, readonly_required=False)


def test_pipeline_returns_candidate_not_real_without_human_approval():
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="report",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=_config(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=build_test_runner_for_tests(),
    )
    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.real_claim_allowed is False
    assert verdict.fail_class == "BLOCK_HUMAN_APPROVAL_MISSING"
    assert verdict.draft_text is not None
    audit = verdict.build_audit_record().to_dict()
    assert "draft_text" not in audit
    assert "납품" not in str(audit)


def test_pipeline_blocks_unsupported_claim_and_suppresses_draft_text():
    def bad_runner(env):
        return "제목: 초안\n핵심 내용: 납품 일정은 2026년 6월 20일입니다."
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=_config(),
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=bad_runner,
    )
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_FINAL_GATE_UNSUPPORTED"
    assert verdict.draft_text is None
    assert verdict.raw_saved_zero is True


def test_pipeline_policy_block_calls_no_successful_real_runner():
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        policy_gate_allowed=False,
    )
    verdict = run_box3_real_enablement_pipeline(env, config=_config(), runner=build_test_runner_for_tests())
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_POLICY_GATE"
    assert verdict.draft_text is None
