from __future__ import annotations

from butler_pc_core.cards.box3.actual_contracts import Box3ActualRuntimeEnvelope
from butler_pc_core.cards.box3.actual_operation_pipeline import run_box3_actual_operation
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard
from butler_pc_core.cards.box3.local_sealed_runner import build_deterministic_test_runner
from butler_pc_core.cards.box3.human_approval_sealed import default_locked_human_approval


def _env():
    return Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="보고서",
    )


def test_pipeline_with_missing_model_authority_is_not_pass():
    env = _env()
    verdict = run_box3_actual_operation(env, helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"))
    assert verdict.status == "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"
    assert verdict.real_claim_allowed is False


def test_pipeline_with_test_runner_remains_candidate_not_real():
    env = _env()
    verdict = run_box3_actual_operation(
        env,
        helper_component_guard=build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk"),
        human_approval_config=default_locked_human_approval(env.request_digest),
        fixed_eval_pass=True,
        runner=build_deterministic_test_runner(),
    )
    assert verdict.status == "REAL_CANDIDATE"
    assert verdict.real_claim_allowed is False
    assert verdict.draft_text is not None
    assert "draft_text" not in verdict.to_persistable_dict()


def test_policy_gate_blocks_before_runner():
    env = Box3ActualRuntimeEnvelope.from_raw(
        reference_texts=["참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다."],
        drafting_request="보고서 초안 작성",
        policy_gate_allowed=False,
    )
    verdict = run_box3_actual_operation(env, runner=build_deterministic_test_runner())
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_POLICY_GATE"
    assert verdict.draft_text is None
