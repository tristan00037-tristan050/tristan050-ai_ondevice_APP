from __future__ import annotations

import json

from butler_pc_core.cards.box4.review_service import (
    CONFIDENCES,
    ISSUE_TYPES,
    SCHEMA_VERSION,
    DocumentReviewInput,
    _extract_json_object,
    review_document,
)


class FakeModelClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, max_tokens: int = 2048) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response, ensure_ascii=False)


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "issues": [
            {
                "location": "계약서 제2조",
                "issue_type": "INCONSISTENCY",
                "original_text": "납품일은 7월 10일로 한다.",
                "suggestion": "참고 문서의 납품일과 맞춰 7월 12일 여부를 확인하십시오.",
                "confidence": "HIGH",
            }
        ],
        "overall_score": 82,
        "summary": "참고 문서와 납품일 표현이 다릅니다.",
        "review_required": True,
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_review_document_accepts_valid_schema() -> None:
    client = FakeModelClient(valid_payload())
    result = review_document(
        DocumentReviewInput(
            target_document="계약서 제2조: 납품일은 7월 10일로 한다.",
            reference_documents=["발주서: 납품 예정일 7월 12일"],
        ),
        model_client=client,
    )

    assert result.schema_version == SCHEMA_VERSION
    assert result.overall_score == 82
    assert result.issues[0]["issue_type"] == "INCONSISTENCY"
    assert result.review_required is True
    assert result.raw_log_zero is True
    assert result.external_send_zero is True
    assert "발주서" in client.prompts[0]


def test_review_document_allows_no_issue_json_only() -> None:
    result = review_document(
        DocumentReviewInput(target_document="완성된 공문입니다.", reference_documents=[]),
        model_client=FakeModelClient(
            valid_payload(
                issues=[],
                overall_score=100,
                summary="추가 지적 사항이 없습니다.",
                review_required=False,
            )
        ),
    )

    assert result.issues == []
    assert result.overall_score == 100
    assert result.review_required is False


def test_extract_json_object_uses_first_balanced_object() -> None:
    parsed = _extract_json_object('prefix {"a": {"b": "brace } in string"}} suffix {"c": 1}')

    assert parsed == {"a": {"b": "brace } in string"}}


def test_review_document_rejects_invalid_json_fail_closed() -> None:
    result = review_document(
        DocumentReviewInput(target_document="검토 대상", reference_documents=[]),
        model_client=FakeModelClient("오류 없습니다."),
    )

    assert result.review_required is True
    assert result.issues == []
    assert result.warnings == ["MODEL_JSON_NOT_FOUND"]
    assert result.raw_log_zero is True


def test_review_document_rejects_bad_enum_fail_closed() -> None:
    bad = valid_payload(
        issues=[
            {
                "location": "본문",
                "issue_type": "WRONG",
                "original_text": "원문",
                "suggestion": "수정",
                "confidence": "HIGH",
            }
        ]
    )

    result = review_document(
        DocumentReviewInput(target_document="검토 대상", reference_documents=[]),
        model_client=FakeModelClient(bad),
    )

    assert result.review_required is True
    assert result.warnings == ["ISSUE_TYPE_INVALID"]


def test_review_document_rejects_original_text_length_fail_closed() -> None:
    issue = dict(valid_payload()["issues"][0])  # type: ignore[index]
    issue["original_text"] = "가" * 301

    result = review_document(
        DocumentReviewInput(target_document="검토 대상", reference_documents=[]),
        model_client=FakeModelClient(valid_payload(issues=[issue])),
    )

    assert result.review_required is True
    assert result.warnings == ["ORIGINAL_TEXT_INVALID_TOO_LONG"]


def test_review_document_redacts_secret_echoes() -> None:
    issue = dict(valid_payload()["issues"][0])  # type: ignore[index]
    issue["original_text"] = "비밀번호는 정책1234야"
    issue["suggestion"] = "API key: sk-secret1234567890 을 제거하십시오."

    result = review_document(
        DocumentReviewInput(target_document="검토 대상", reference_documents=[]),
        model_client=FakeModelClient(valid_payload(issues=[issue])),
    )

    dumped = json.dumps(result.to_payload(), ensure_ascii=False)
    assert "정책1234" not in dumped
    assert "sk-secret1234567890" not in dumped
    assert "[민감정보 원문 생략]" in dumped


def test_review_contract_enums_are_sealed() -> None:
    assert ISSUE_TYPES == {"MISSING", "ERROR", "INCONSISTENCY", "STYLE", "SUGGESTION"}
    assert CONFIDENCES == {"HIGH", "MEDIUM", "LOW"}
