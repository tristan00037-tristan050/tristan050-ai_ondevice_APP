from __future__ import annotations

import json

from butler_pc_core.cards.box6.form_fill_service import (
    BOX6_JSON_SCHEMA,
    CONFIDENCES,
    REQUIRED_MAPPING_KEYS,
    REQUIRED_TOP_LEVEL_KEYS,
    SAFE_SECRET_REPLACEMENT,
    SCHEMA_VERSION,
    FormFillInput,
    fill_form,
)
from butler_pc_core.runtime.json_grammar import GrammarUnavailable


class FakeModelClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.grammars: list[object] = []

    def generate(self, prompt: str, *, max_tokens: int = 2048, grammar: object | None = None) -> str:
        self.prompts.append(prompt)
        if grammar is None:
            raise AssertionError("Box6 structured path must pass grammar")
        self.grammars.append(grammar)
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response, ensure_ascii=False)


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "filled_form": "납품업체명: 주식회사 버틀러\n대표이사: ___",
        "field_mappings": [
            {
                "target_label": "납품업체명",
                "output_value": "주식회사 버틀러",
                "confidence": "HIGH",
                "source_ref": "our_data.회사명",
                "reason_code": "LABEL_SEMANTIC_MATCH",
            },
            {
                "target_label": "대표이사",
                "output_value": "",
                "confidence": "UNFILLED",
                "source_ref": "",
                "reason_code": "NO_SOURCE_VALUE",
            },
        ],
        "unfilled_fields": ["대표이사"],
        "review_required": ["대표이사"],
        "warnings": ["근거 없는 항목은 UNFILLED 처리했습니다."],
    }
    payload.update(overrides)
    return payload


def test_fill_form_accepts_valid_schema() -> None:
    client = FakeModelClient(valid_payload())

    result = fill_form(
        FormFillInput(
            blank_form="납품업체명: ___\n대표이사: ___",
            data_documents=["회사명: 주식회사 버틀러"],
        ),
        model_client=client,
    )

    assert result.schema_version == SCHEMA_VERSION
    assert result.field_mappings[0]["confidence"] == "HIGH"
    assert result.review_required == ["대표이사"]
    assert client.grammars
    assert "## 빈 외부 양식" in client.prompts[0]
    assert "/no_think" in client.prompts[0]


def test_fill_form_emits_raw_zero_telemetry_on_success(monkeypatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service._log_structured_telemetry", events.append)

    result = fill_form(
        FormFillInput(blank_form="납품업체명: ___", data_documents=["회사명: 주식회사 버틀러"]),
        model_client=FakeModelClient(valid_payload()),
    )

    assert result.schema_version == SCHEMA_VERSION
    assert events
    event = events[0]
    assert event["card_mode"] == "6"
    assert event["grammar_required"] is True
    assert event["grammar_applied"] is True
    assert event["reason_code"] == ""
    assert event["raw_text_logged"] is False
    assert event["external_send_zero"] is True
    assert "주식회사 버틀러" not in json.dumps(event, ensure_ascii=False)


def test_fill_form_rejects_non_json_fail_closed() -> None:
    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient("양식 채우기가 완료되었습니다."),
    )

    assert result.filled_form == ""
    assert result.review_required == ["결과 형식 확인"]
    assert result.warnings == ["MODEL_JSON_NOT_FOUND"]


def test_fill_form_emits_reason_code_telemetry_on_schema_failure(monkeypatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service._log_structured_telemetry", events.append)

    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload(raw_response="원문")),
    )

    assert result.warnings == ["SCHEMA_KEYS_INVALID"]
    assert any(event["reason_code"] == "SCHEMA_KEYS_INVALID" for event in events)
    assert all(event["raw_text_logged"] is False for event in events)
    assert "원문" not in json.dumps(events, ensure_ascii=False)


def test_fill_form_fails_closed_when_grammar_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")

    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", unavailable)

    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload()),
    )

    assert result.warnings == ["GRAMMAR_UNAVAILABLE"]


def test_fill_form_fails_closed_when_model_client_cannot_accept_grammar() -> None:
    class LegacyClient:
        def generate(self, prompt: str, *, max_tokens: int = 2048) -> str:
            return json.dumps(valid_payload(), ensure_ascii=False)

    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=LegacyClient(),
    )

    assert result.warnings == ["GRAMMAR_UNAVAILABLE"]


def test_fill_form_rejects_legacy_mapping_schema() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping["source_excerpt"] = "원문 일부"

    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload(field_mappings=[mapping])),
    )

    assert result.warnings == ["LEGACY_MAPPING_SCHEMA"]


def test_fill_form_rejects_top_level_extra_key() -> None:
    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload(raw_response="원문")),
    )

    assert result.warnings == ["SCHEMA_KEYS_INVALID"]


def test_fill_form_blocks_secret_label_real_value_without_review_markers() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping.update(
        {
            "target_label": "API 키",
            "output_value": "plain-secret-1234",
            "confidence": "HIGH",
            "source_ref": "our_data.api_key",
        }
    )

    result = fill_form(
        FormFillInput(blank_form="API 키: ___", data_documents=["API 키: plain-secret-1234"]),
        model_client=FakeModelClient(
            valid_payload(field_mappings=[mapping], unfilled_fields=[], review_required=[], warnings=[])
        ),
    )

    assert result.filled_form == ""
    assert result.warnings == ["SENSITIVE_FIELD_AUTOFILL_BLOCKED"]


def test_fill_form_allows_secret_label_only_when_unfilled_and_listed() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping.update(
        {
            "target_label": "비밀번호",
            "output_value": "UNFILLED",
            "confidence": "UNFILLED",
            "source_ref": "",
            "reason_code": "SENSITIVE_FIELD_REQUIRES_MANUAL_INPUT",
        }
    )

    result = fill_form(
        FormFillInput(blank_form="비밀번호: ___", data_documents=["비밀번호: plain-secret-1234"]),
        model_client=FakeModelClient(
            valid_payload(
                field_mappings=[mapping],
                unfilled_fields=["비밀번호"],
                review_required=["비밀번호"],
                warnings=["민감 필드는 수동 확인이 필요합니다."],
            )
        ),
    )

    assert result.warnings == ["민감 필드는 수동 확인이 필요합니다."]
    assert result.field_mappings[0]["output_value"] == "UNFILLED"


def test_fill_form_quarantines_secret_real_value_when_review_listed() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping.update(
        {
            "target_label": "API 키",
            "output_value": "plain-secret-1234",
            "confidence": "LOW",
            "source_ref": "our_data.api_key",
            "reason_code": "SENSITIVE_FIELD_REQUIRES_MANUAL_INPUT",
        }
    )

    result = fill_form(
        FormFillInput(blank_form="API 키: ___", data_documents=["API 키: plain-secret-1234"]),
        model_client=FakeModelClient(
            valid_payload(
                field_mappings=[mapping],
                unfilled_fields=["API 키"],
                review_required=["API 키"],
                warnings=["민감 필드는 수동 확인이 필요합니다."],
            )
        ),
    )

    assert result.filled_form != ""
    assert result.field_mappings[0]["output_value"] == SAFE_SECRET_REPLACEMENT
    assert "plain-secret-1234" not in json.dumps(result.to_payload(), ensure_ascii=False)


def test_box6_json_schema_matches_backend_contract() -> None:
    assert set(BOX6_JSON_SCHEMA["required"]) == REQUIRED_TOP_LEVEL_KEYS
    mapping_schema = BOX6_JSON_SCHEMA["properties"]["field_mappings"]["items"]  # type: ignore[index]
    assert set(mapping_schema["required"]) == REQUIRED_MAPPING_KEYS
    assert BOX6_JSON_SCHEMA["properties"]["review_required"]["type"] == "array"  # type: ignore[index]
    assert set(mapping_schema["properties"]["confidence"]["enum"]) == CONFIDENCES  # type: ignore[index]
    assert BOX6_JSON_SCHEMA["additionalProperties"] is False
    assert mapping_schema["additionalProperties"] is False
