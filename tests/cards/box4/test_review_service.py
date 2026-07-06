from __future__ import annotations

import json

from butler_pc_core.cards.box4.review_service import SCHEMA_VERSION, DocumentReviewInput, _extract_json_object, review_document


class FakeModel:
    def __init__(self, payload: str):
        self.payload = payload
        self.seen_prompt = ""

    def generate(self, prompt: str) -> str:
        self.seen_prompt = prompt
        return self.payload


def _valid_payload(**updates):
    issue = {
        "location": "1조",
        "issue_type": "MISSING",
        "original_text": "납기 조항 없음",
        "suggestion": "납기 조항을 추가하십시오.",
        "confidence": "HIGH",
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "issues": [issue],
        "overall_score": 80,
        "summary": "납기 조항 보완이 필요합니다.",
        "review_required": True,
        "warnings": [],
    }
    payload.update(updates)
    return payload


def test_extract_json_object_accepts_fenced_json_only():
    data = _extract_json_object("```json\n" + json.dumps(_valid_payload(), ensure_ascii=False) + "\n```")
    assert data["schema_version"] == SCHEMA_VERSION


def test_review_document_valid_payload_passes():
    model = FakeModel(json.dumps(_valid_payload(), ensure_ascii=False))
    result = review_document(DocumentReviewInput("계약서 초안", []), model_client=model)
    assert result.schema_version == SCHEMA_VERSION
    assert result.issues[0]["issue_type"] == "MISSING"
    assert result.external_send_zero is True
    assert result.raw_log_zero is True
    assert "계약서 초안" in model.seen_prompt


def test_review_document_rejects_invalid_json_fail_closed():
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeModel("오류 없음"))
    assert result.review_required is True
    assert result.issues == []
    assert result.warnings


def test_review_document_rejects_bad_enum_fail_closed():
    bad_issue = dict(_valid_payload()["issues"][0], issue_type="BAD")
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeModel(json.dumps(_valid_payload(issues=[bad_issue]), ensure_ascii=False)))
    assert result.review_required is True
    assert result.warnings[0] == "ISSUE_TYPE_INVALID"


def test_original_text_length_guard():
    long_issue = dict(_valid_payload()["issues"][0], original_text="가" * 301)
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeModel(json.dumps(_valid_payload(issues=[long_issue]), ensure_ascii=False)))
    assert result.review_required is True
    assert result.warnings[0] == "ORIGINAL_TEXT_TOO_LONG"


def test_model_cannot_claim_no_issue_with_low_score():
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeModel(json.dumps(_valid_payload(issues=[], overall_score=70, review_required=False), ensure_ascii=False)))
    assert result.review_required is True
    assert result.warnings[0] == "NO_ISSUE_LOW_SCORE_INVALID"
