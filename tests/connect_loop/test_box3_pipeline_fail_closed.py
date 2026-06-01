"""PR #770 box3 fail-closed 회귀 방지 (Codex P2 #1 + P1 #3, + P1 #2 잠금).

대상 결함(2026-06-01 실측 재현 후 정정):
  #1 (P2) grounding/pipeline.py: contract_only 변수만 보고 draft_text 를 suppress 하여
     _determine_status 의 final demotion(asset incomplete)을 무시하던 누출.
  #3 (P1) pipeline.py L73-74: fail_class 가 format/style adapter fail-closed 신호를
     무시하여 format_match_score:0.0 / forbidden_style_zero:false 인 draft 가 status="real"
     로 통과하던 결함.
  #2 (P1) draft_service.py: real_model_runner 호출 전 BOX3_DIGEST_ONLY_INPUT + sha256 강제
     (commit c420d563 v1.2.1 P0 에서 이미 정정됨 — 본 테스트는 그 계약을 잠근다).

함수명/시그니처/필드는 모두 실측(View) 기준. 추정 0.
"""
from __future__ import annotations

import pytest

# ── #1: grounding/pipeline (force/runner 입력 + Box3PipelineInput 계약) ──────────
from butler_pc_core.cards.box3.grounding.pipeline import (
    Box3PipelineInput,
    Box3ReferenceDoc,
    digest_text,
    run_box3_pipeline as run_grounding_box3_pipeline,
)

# ── #3: pipeline (Box3Request 계약 + 주입 runner) ──────────────────────────────
from butler_pc_core.cards.box3.pipeline import run_box3_pipeline
from butler_pc_core.cards.box3.types import Box3Request

# ── #2: draft_service digest-only 계약 ─────────────────────────────────────────
from butler_pc_core.cards.box3.draft_service import (
    Box3ContractError,
    draft_from_current_contract,
)


# 모든 필수 섹션 + 정중체 + forbidden 0 → format/style/grounding 통과(유일한 real 경로 입력).
_CLEAN_REAL_DRAFT = "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"


def _passing_real_manifest() -> dict:
    assets = []
    for index, name in enumerate(
        ["helper3_format", "helper4_grounding", "helper7_table_figure", "helper8_company_style"],
        start=1,
    ):
        assets.append(
            {
                "asset_name": name,
                "role": name,
                "display_sha_prefix": f"{index:08x}...",
                "asset_path": f"/runtime/{name}",
                "sha256_full": f"{index}" * 64,
                "sha_scope": "file",
                "measured_at": "2026-06-01T00:00:00+00:00",
                "measured_by": "test",
                "source_metadata_files": ["adapter_config.json"],
                "interface_inventory_status": "pass",
                "real_claim_allowed": True,
                "fail_class": None,
            }
        )
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": "ASSET_INVENTORY_PASS",
        "real_claim_allowed": True,
        "assets": assets,
    }


def _request() -> Box3Request:
    return Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request")


# ───────────────────────────────────────────────────────────────────────────────
# 결함 #1 (P2) — grounding/pipeline contract_only demote 시 draft_text suppress
# ───────────────────────────────────────────────────────────────────────────────
def test_grounding_runner_path_demoted_to_contract_only_suppresses_draft_text():
    """runner 가 주입되어 contract_only 변수는 False 지만, default manifest 가 incomplete 라
    final status 가 contract_only 로 demote 되는 경로. draft_text 가 누출되면 안 된다(#1 핵심)."""
    def runner(prompt, config):
        return "제목\n목적\n근거\n초안\n확인 필요\n본문 합니다"  # grounding/format/style 통과 입력

    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="근거 문서")],
    )
    result = run_grounding_box3_pipeline(payload, runner=runner).to_dict()

    assert result["status"] == "contract_only"
    assert result["contract_only"] is False  # 변수는 origin(runner) 기준 그대로 False
    assert result["draft_text"] is None, f"contract_only demote 시 draft_text 누출: {result['draft_text']!r}"
    assert result["draft_digest"] is not None  # digest/meta 는 유지


def test_grounding_force_draft_text_path_still_suppresses():
    """force_draft_text(contract_only=True) 경로 무회귀 — 여전히 draft_text None."""
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="근거 문서")],
    )
    result = run_grounding_box3_pipeline(payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요").to_dict()
    assert result["draft_text"] is None


# ───────────────────────────────────────────────────────────────────────────────
# 결함 #3 (P1) — pipeline format/style fail-closed gate
# ───────────────────────────────────────────────────────────────────────────────
def test_pipeline_format_fail_blocks_real_status():
    """필수 섹션 누락(format_match_score 미달) → status="real" 차단(#3 핵심)."""
    def runner(prompt, max_new_tokens):
        return "오늘 회의 결과를 정리한 내용입니다"  # 섹션 미충족, PII/forbidden 0

    result = run_box3_pipeline(_request(), asset_manifest=_passing_real_manifest(), real_model_runner=runner)
    assert result["status"] == "contract_only"
    assert result["fail_class"] == "FORMAT_MATCH_BELOW_GATE"
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None
    assert result["format"]["required_sections_present"] is False


def test_pipeline_forbidden_style_blocks_real_status():
    """forbidden_style_zero=false → status="real" 차단."""
    def runner(prompt, max_new_tokens):
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n확정합니다"  # '확정합니다' = forbidden

    result = run_box3_pipeline(_request(), asset_manifest=_passing_real_manifest(), real_model_runner=runner)
    assert result["status"] == "contract_only"
    assert result["fail_class"] == "FORBIDDEN_STYLE_DETECTED"
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None
    assert result["style"]["forbidden_style_zero"] is False


def test_pipeline_clean_draft_with_passing_manifest_is_real():
    """format/style/grounding 모두 통과 + passing manifest + runner → 유일한 real 경로(무회귀)."""
    def runner(prompt, max_new_tokens):
        assert "BOX3_DIGEST_ONLY_INPUT" in prompt
        return _CLEAN_REAL_DRAFT

    result = run_box3_pipeline(_request(), asset_manifest=_passing_real_manifest(), real_model_runner=runner)
    assert result["status"] == "real"
    assert result["fail_class"] is None
    assert result["real_claim_allowed"] is True
    assert result["draft_text"] is not None


# ───────────────────────────────────────────────────────────────────────────────
# 결함 #2 (P1) — digest-only input enforce (이미 정정됨, 계약 잠금)
# ───────────────────────────────────────────────────────────────────────────────
def test_draft_service_raw_prose_blocked_before_real_runner():
    """raw business prose(PII/secrets/paths 0)도 BOX3_DIGEST_ONLY_INPUT 아니면 runner 도달 전 BLOCK."""
    calls = []

    def runner(prompt, max_new_tokens):
        calls.append(prompt)
        return "draft"

    raw_input = "당사는 이번 분기 매출이 전년 대비 12% 증가하였습니다. 이에 대한 보고서 초안을 작성합니다."
    prompt_template = "Box3 draft. Input: {input}"

    with pytest.raises(Box3ContractError) as exc:
        draft_from_current_contract(
            input_text=raw_input,
            prompt_template=prompt_template,
            max_new_tokens=512,
            real_model_runner=runner,
        )
    assert str(exc.value) == "DIGEST_ONLY_INPUT_REQUIRED_FOR_REAL_RUNNER"
    assert calls == [], "raw input 이 real_model_runner 에 도달하면 안 된다"
    # error 에 raw input 원문이 새지 않아야 한다(no-raw-output 정합).
    assert "매출" not in str(exc.value)
