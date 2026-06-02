
from __future__ import annotations

from butler_pc_core.cards.box3.grounding.pipeline import Box3PipelineInput, Box3ReferenceDoc, digest_text, run_box3_pipeline

def test_grounding_fail_closed_needs_review():
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="근거 문서")],
    )
    result = run_box3_pipeline(payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요\nUNSUPPORTED_CLAIM").to_dict()
    assert result["status"] == "needs_review"
    assert result["fail_class"] == "UNSUPPORTED_CLAIM_DETECTED"
    assert result["grounding"]["unsupported_claim_rate"] == 1.0

def test_no_evidence_blocks_or_reviews():
    payload = Box3PipelineInput(request_text="새 초안 작성", reference_docs=[])
    result = run_box3_pipeline(payload, force_draft_text="제목\n목적\n근거\n초안\n확인 필요").to_dict()
    assert result["status"] == "needs_review"
    assert result["fail_class"] == "NO_EVIDENCE_UNITS"

def test_empty_draft_blocks():
    payload = Box3PipelineInput(
        request_text="새 초안 작성",
        reference_docs=[Box3ReferenceDoc(source_digest=digest_text("source"), runtime_text="근거 문서")],
    )
    result = run_box3_pipeline(payload, force_draft_text="").to_dict()
    assert result["status"] == "blocked"
    assert result["fail_class"] == "DRAFT_EMPTY"
