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

