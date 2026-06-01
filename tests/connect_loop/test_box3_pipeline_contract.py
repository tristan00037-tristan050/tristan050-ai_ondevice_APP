from butler_pc_core.cards.box3.pipeline import run_box3_pipeline
from butler_pc_core.cards.box3.security import is_sha256_digest
from butler_pc_core.cards.box3.types import Box3Request


def test_pipeline_smoke_runs_five_steps_contract_only():
    result = run_box3_pipeline(
        Box3Request(
            reference_docs=["digest-safe reference alpha", "digest-safe reference beta <table>x</table>"],
            draft_request="digest-safe request",
            format_hint="report",
        )
    )
    assert result["status"] == "contract_only"
    assert result["contract_only"] is True
    assert result["real_claim_allowed"] is False
    assert result["external_send_zero"] is True
    assert result["raw_saved_zero"] is True
    assert result["raw_doc_logged"] is False
    assert result["draft_text"] is None
    assert is_sha256_digest(result["draft_digest"])
    assert result["citations"]
    assert all(is_sha256_digest(item["source_digest"]) for item in result["citations"])
    assert result["grounding"]["reference_coverage"] >= 0.80
    assert result["format"]["format_match_score"] >= 0.85
    assert result["style"]["style_match_score"] >= 0.70


def test_grounding_fail_closed_when_unsupported_claims_injected():
    result = run_box3_pipeline(
        Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request"),
        injected_unsupported_claim_count=2,
    )
    assert result["status"] in {"needs_review", "blocked"}
    assert result["fail_class"] == "GROUNDING_UNSUPPORTED_CLAIM_RATE_EXCEEDED"
    assert result["grounding"]["unsupported_claim_rate"] > 0.03
    assert result["contract_only"] is True
    assert result["real_claim_allowed"] is False


def _passing_real_manifest():
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


def test_passing_manifest_without_runner_keeps_real_flags_closed():
    result = run_box3_pipeline(
        Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request"),
        asset_manifest=_passing_real_manifest(),
    )
    assert result["status"] == "contract_only"
    assert result["contract_only"] is True
    assert result["real_claim_allowed"] is False
    assert result["draft_text"] is None
    assert result["fail_class"] == "ASSET_INTERFACE_PENDING"


def test_incomplete_manifest_suppresses_forced_real_runner_output():
    def runner(prompt, max_new_tokens):
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"

    result = run_box3_pipeline(
        Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request"),
        real_model_runner=runner,
    )
    assert result["status"] == "contract_only"
    assert result["draft_text"] is None
    assert result["contract_only"] is True
    assert result["real_claim_allowed"] is False


def test_passing_manifest_with_runner_is_the_only_real_claim_path():
    def runner(prompt, max_new_tokens):
        assert "BOX3_DIGEST_ONLY_INPUT" in prompt
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"

    result = run_box3_pipeline(
        Box3Request(reference_docs=["digest-safe reference"], draft_request="digest-safe request"),
        asset_manifest=_passing_real_manifest(),
        real_model_runner=runner,
    )
    assert result["status"] == "real"
    assert result["contract_only"] is False
    assert result["real_claim_allowed"] is True
    assert result["draft_text"] is not None
