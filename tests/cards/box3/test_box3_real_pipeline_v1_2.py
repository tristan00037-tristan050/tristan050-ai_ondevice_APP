from __future__ import annotations

from dataclasses import asdict

from butler_pc_core.cards.box3.asset_manifest import (
    ASSET_INVENTORY_PASS_STATUS,
    Box3AssetRecord,
    REQUIRED_ASSET_NAMES,
)
from butler_pc_core.cards.box3.real_contract import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.real_pipeline import run_box3_real_followup
from butler_pc_core.cards.box3.security import assert_no_raw_persistence


def _passing_manifest() -> dict:
    assets = []
    for index, name in enumerate(REQUIRED_ASSET_NAMES):
        sha_char = "abcdef0123456789"[index]
        assets.append(
            asdict(
                Box3AssetRecord(
                    asset_name=name,
                    role=f"{name}_role",
                    display_sha_prefix=f"{sha_char * 8}...",
                    asset_path=f"ref:BOX3_{name.upper()}_PATH",
                    sha256_full=sha_char * 64,
                    sha_scope="file",
                    measured_at="2026-06-02T00:00:00+00:00",
                    measured_by="test_fixture",
                    source_metadata_files=["adapter_config.json"],
                    interface_inventory_status="pass",
                    real_claim_allowed=True,
                    fail_class=None,
                )
            )
        )
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": ASSET_INVENTORY_PASS_STATUS,
        "real_claim_allowed": True,
        "state_gate": "ASSET_INVENTORY_PASS",
        "created_at": "2026-06-02T00:00:00+00:00",
        "assets": assets,
        "asset_errors": {},
    }


def _envelope(reference_texts: list[str] | None = None) -> Box3RealRuntimeEnvelope:
    return Box3RealRuntimeEnvelope.from_raw(
        request_text="프로젝트 알파 실행 초안을 작성합니다",
        reference_texts=reference_texts
        if reference_texts is not None
        else [
            "프로젝트 알파는 내부 검토를 완료했습니다. 담당 조직은 운영팀입니다.",
            "프로젝트 알파는 내부 검토를 완료했습니다.",
        ],
        company_format_text="제목, 배경, 핵심 내용, 근거, 확인 필요, 최종 문안 순서",
    )


def _supported_draft(_envelope: Box3RealRuntimeEnvelope) -> str:
    return "\n".join(
        [
            "제목: 프로젝트 알파 실행 초안",
            "배경: 프로젝트 알파는 내부 검토를 완료했습니다.",
            "핵심 내용: 담당 조직은 운영팀입니다.",
            "근거: source_digest 기준으로만 표시합니다.",
            "확인 필요: 추가 일정은 확인 필요입니다.",
            "최종 문안: 프로젝트 알파는 내부 검토를 완료했습니다.",
        ]
    )


def test_real_pipeline_contract_only_manifest_does_not_call_runner():
    called = {"value": False}

    def runner(_envelope: Box3RealRuntimeEnvelope) -> str:
        called["value"] = True
        return _supported_draft(_envelope)

    output = run_box3_real_followup(_envelope(), real_model_runner=runner)

    assert output.verdict.status == "contract_only"
    assert output.verdict.real_claim_allowed is False
    assert output.verdict.fail_class == "ASSET_INTERFACE_PENDING"
    assert output.verdict.draft_text is None
    assert called["value"] is False


def test_real_pipeline_blocks_no_evidence_before_runner():
    called = {"value": False}

    def runner(_envelope: Box3RealRuntimeEnvelope) -> str:
        called["value"] = True
        return _supported_draft(_envelope)

    output = run_box3_real_followup(
        _envelope(reference_texts=[]),
        asset_manifest=_passing_manifest(),
        real_model_runner=runner,
        fixed_eval_sample_count=40,
    )

    assert output.verdict.status == "needs_review"
    assert output.verdict.fail_class == "NO_EVIDENCE_UNITS"
    assert output.verdict.draft_text is None
    assert called["value"] is False


def test_real_pipeline_blocks_unsupported_claim_and_suppresses_draft_text():
    def runner(_envelope: Box3RealRuntimeEnvelope) -> str:
        return "\n".join(
            [
                "제목: 프로젝트 알파 실행 초안",
                "배경: 프로젝트 알파는 내부 검토를 완료했습니다.",
                "핵심 내용: 신규 예산은 확정되었습니다.",
                "근거: source_digest 기준으로만 표시합니다.",
                "확인 필요: 추가 일정은 확인 필요입니다.",
                "최종 문안: 프로젝트 알파는 내부 검토를 완료했습니다.",
            ]
        )

    output = run_box3_real_followup(
        _envelope(),
        asset_manifest=_passing_manifest(),
        real_model_runner=runner,
        fixed_eval_sample_count=40,
    )

    assert output.verdict.status == "blocked"
    assert output.verdict.fail_class == "BLOCK_UNSUPPORTED_CLAIM"
    assert output.verdict.draft_text is None
    assert output.verdict.real_claim_allowed is False
    assert any(item["support_level"] == "unsupported" for item in output.verdict.claim_verdicts)


def test_real_pipeline_needs_review_when_fixed_eval_gate_not_met():
    output = run_box3_real_followup(
        _envelope(),
        asset_manifest=_passing_manifest(),
        real_model_runner=_supported_draft,
        fixed_eval_sample_count=39,
    )

    assert output.verdict.status == "needs_review"
    assert output.verdict.fail_class == "FIXED_EVAL_SAMPLE_COUNT_BELOW_GATE"
    assert output.verdict.draft_text is None
    assert output.verdict.metrics["fixed_eval_sample_count"] == 39


def test_real_pipeline_passes_only_when_assets_runner_claims_and_metrics_pass():
    output = run_box3_real_followup(
        _envelope(),
        asset_manifest=_passing_manifest(),
        real_model_runner=_supported_draft,
        fixed_eval_sample_count=40,
    )

    assert output.verdict.status == "real"
    assert output.verdict.real_claim_allowed is True
    assert output.verdict.contract_only is False
    assert output.verdict.draft_text is not None
    assert output.verdict.metrics["pass"] is True
    assert output.verdict.metrics["unsupported_claim_rate"] == 0.0
    assert output.verdict.metrics["citation_accuracy"] == 1.0
    assert output.verdict.metrics["format_match_score"] >= 0.85
    assert output.verdict.metrics["style_match_score"] >= 0.70
    assert output.audit.to_dict()["draft_digest"] == output.verdict.draft_digest
    assert_no_raw_persistence(output.to_persistable_dict())
