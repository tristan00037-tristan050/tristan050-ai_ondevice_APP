from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.real_contracts import (
    Box3RealRuntimeEnvelope,
    ClaimVerdict,
    Box3RealStatus,
    assert_audit_record_is_digest_only,
    sha256_text,
    validate_box3_real_status_transition,
)


def test_runtime_envelope_from_raw_reference_texts_digest_without_persisting_raw():
    env = Box3RealRuntimeEnvelope.from_raw(
        reference_texts=["납품 일정은 2026년 6월 10일입니다."],
        drafting_request="위 내용을 보고서 초안으로 작성",
        format_hint="report",
    )
    assert env.request_digest.startswith("sha256:")
    assert env.reference_digests[0] == sha256_text("납품 일정은 2026년 6월 10일입니다.")
    seed = env.to_audit_seed()
    assert "reference_text_runtime_only" not in str(seed)
    assert "납품" not in str(seed)


def test_runtime_envelope_reference_docs_kwarg_forbidden():
    with pytest.raises(TypeError):
        Box3RealRuntimeEnvelope.from_raw(
            reference_docs=["구 시그니처는 금지"],  # type: ignore[call-arg]
            drafting_request="초안 작성",
        )


def test_claim_verdict_reason_code_and_evidence_invariants():
    digest = sha256_text("납품 일정은 2026년 6월 10일입니다.")
    evidence_digest = sha256_text("근거")
    ok = ClaimVerdict("c1", digest, "supported", [evidence_digest], 0.9, "EVIDENCE_ENTAILS")
    assert ok.support_level == "supported"
    with pytest.raises(ValueError, match="CLAIM_VERDICT_INCONSISTENT"):
        ClaimVerdict("c2", digest, "supported", [], 0.5, "NO_MATCHING_EVIDENCE")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="CLAIM_VERDICT_INCONSISTENT"):
        ClaimVerdict("c3", digest, "no_evidence", [evidence_digest], 0.5, "NO_MATCHING_EVIDENCE")


def test_audit_record_rejects_raw_text():
    with pytest.raises(AssertionError):
        assert_audit_record_is_digest_only({"request_digest": sha256_text("x"), "draft_text": "raw draft"})


def test_status_literal_ssot_and_invalid_transition_blocks():
    allowed = set(Box3RealStatus.__args__)  # type: ignore[attr-defined]
    assert allowed == {
        "CONTRACT_ONLY",
        "ASSET_INVENTORY_PASS",
        "REAL_CANDIDATE",
        "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL",
        "BLOCKED",
        "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE",
    }
    with pytest.raises(ValueError):
        validate_box3_real_status_transition("CONTRACT_ONLY", "PASS_" + "BOX3_REAL")
    with pytest.raises(ValueError):
        validate_box3_real_status_transition("CONTRACT_ONLY", "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL")
