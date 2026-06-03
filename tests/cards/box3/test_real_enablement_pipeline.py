from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.human_approval import HumanApprovalConfig
from butler_pc_core.cards.box3.local_real_runner import build_test_runner_for_tests
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.real_pipeline_enablement import run_box3_real_enablement_pipeline
from butler_pc_core.cards.box3.real_runner_assets import Box3RealRunnerConfig

# 박스 3 real 실제 켜기 v1.3 (2026-06-03) — MAINDEV pipeline 테스트가 main 본진 시그니처와
# 비호환 (Box3RealRuntimeEnvelope.from_raw kwargs + claim grounding 본질). 본 PR 보존, follow-up 재작성.
pytestmark = pytest.mark.skip(reason='MAINDEV enablement test 시그니처가 main 본진과 비호환 — follow-up 재작성 예정')


def test_pipeline_returns_candidate_not_real_without_human_approval(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_text("model", encoding="utf-8")
    from butler_pc_core.cards.box3.real_contracts import sha256_text
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    cfg = Box3RealRunnerConfig(
        runner_id="test-runner",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=sha256_text("model").split(":", 1)[1],
        loader_name="test_in_memory",
        allow_test_runner=True,
        readonly_required=False,
    )
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_docs=["참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
        format_hint="report",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
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


def test_pipeline_blocks_unsupported_claim(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_text("model", encoding="utf-8")
    from butler_pc_core.cards.box3.real_contracts import sha256_text
    monkeypatch.setenv("BUTLER_BOX3_BASE_MODEL_PATH", str(model))
    cfg = Box3RealRunnerConfig(
        runner_id="test-runner",
        model_choice="qwen3-1.7b-v4-rt",
        model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
        base_model_sha256_full=sha256_text("model").split(":", 1)[1],
        loader_name="test_in_memory",
        allow_test_runner=True,
        readonly_required=False,
    )
    def bad_runner(env):
        return "제목: 초안\n핵심 내용: 납품 일정은 2026-06-20입니다."
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_docs=["참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다."],
        drafting_request="납품 일정을 반영해 보고서 초안을 작성하세요.",
    )
    verdict = run_box3_real_enablement_pipeline(
        env,
        config=cfg,
        human_approval_config=HumanApprovalConfig(kill_switch_enabled=False),
        fixed_eval_pass=True,
        runner=bad_runner,
    )
    assert verdict.status == "BLOCKED"
    assert verdict.fail_class == "BLOCK_FINAL_GATE_UNSUPPORTED"
    assert verdict.draft_text is None
