"""융합 7단계 파이프라인 — contract_only/blocked/needs_review/real, stage_trace, fail-closed."""
from __future__ import annotations

import time

from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.real_pipeline import (
    Box3RealPipelineConfig,
    run_box3_real_followup,
    run_box3_real_pipeline,
)

from ._real_fusion_fixtures import (
    PASSING_REF,
    contract_only_manifest,
    passing_asset_manifest,
    passing_envelope,
    supported_runner,
)

_PASS_CFG = Box3RealPipelineConfig(fixed_eval_pass=True, allow_pass_box3_real_after_human_approval=True)


def test_default_manifest_is_contract_only_and_never_calls_runner():
    called = {"n": 0}

    def runner(_env):
        called["n"] += 1
        return "draft"

    verdict, audit = run_box3_real_pipeline(
        reference_docs=[PASSING_REF], drafting_request="요약", real_model_runner=runner,
    )
    assert verdict.status == "contract_only"
    assert verdict.contract_only is True and verdict.real_claim_allowed is False
    assert called["n"] == 0  # asset PENDING → runner 미호출(real claim closed)
    assert [s["stage"] for s in audit.stage_trace] == ["asset_inventory"]


def test_runner_missing_blocks_after_asset_pass():
    verdict, audit = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=None,
    )
    assert verdict.status == "blocked"
    assert verdict.fail_class == "BLOCK_BOX3_REAL_RUNNER_MISSING"


def test_no_evidence_blocks_before_runner():
    called = {"n": 0}

    def runner(_env):
        called["n"] += 1
        return "draft"

    env = Box3RealRuntimeEnvelope.from_raw(drafting_request="요약", reference_texts=[])
    verdict, _ = run_box3_real_followup(env, asset_manifest=passing_asset_manifest(), real_model_runner=runner)
    assert verdict.status == "blocked"
    assert verdict.fail_class == "BLOCK_EVIDENCE_EXTRACTION_FAILED"
    assert called["n"] == 0


def test_runner_timeout_is_fail_closed():
    def slow(_env):
        time.sleep(0.3)
        return "draft"

    verdict, _ = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=slow,
        config=Box3RealPipelineConfig(timeout_sec=0.05),
    )
    assert verdict.status == "blocked"
    assert verdict.fail_class == "BLOCK_BOX3_REAL_RUNNER_TIMEOUT"


def test_unsupported_claim_blocks_and_suppresses_draft_text():
    def hallucinating(_env):
        return (
            "제목: 보고\n배경: 프로젝트 알파 납품 일정 보고\n"
            "핵심 내용: 계약 금액은 9억원으로 합의되었다\n"  # 근거의 1억원과 모순
            "확인 필요: 없음\n최종 문안: 보고 승인 요청\n"
        )

    verdict, _ = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=hallucinating,
    )
    assert verdict.status == "blocked"
    assert verdict.fail_class == "BLOCK_FINAL_GATE_UNSUPPORTED"
    assert verdict.draft_text is None  # fail-closed: 미지지 시 draft 억제
    assert "draft_text" not in verdict.to_persistable_dict()


def test_clean_real_path_passes_all_seven_stages():
    verdict, audit = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(),
        real_model_runner=supported_runner, config=_PASS_CFG,
    )
    assert verdict.status == "real"
    assert verdict.real_claim_allowed is True and verdict.fail_class is None
    assert verdict.metrics["unsupported_claim_rate"] == 0.0
    assert verdict.metrics["citation_accuracy"] >= 0.95
    assert [s["stage"] for s in audit.stage_trace] == [
        "asset_inventory",
        "helper7_evidence_extraction",
        "draft_runner",
        "claim_extraction",
        "helper4_claim_grounding",
        "helper3_helper8_format_style",
        "final_real_gate",
    ]


def test_real_candidate_without_human_approval():
    # fixed_eval/human approval 미설정 시 메트릭이 통과해도 real_candidate(대표 승인 전 보류).
    verdict, _ = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=supported_runner,
    )
    assert verdict.status == "real_candidate"
    assert verdict.real_claim_allowed is False
