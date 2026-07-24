from __future__ import annotations
import pytest

import json

import pytest

from butler_pc_core.cards.box6.form_fill_service import (
    BOX6_JSON_SCHEMA,
    CONFIDENCES,
    REQUIRED_MAPPING_KEYS,
    REQUIRED_TOP_LEVEL_KEYS,
    SAFE_SECRET_REPLACEMENT,
    SCHEMA_VERSION,
    SENSITIVE_FIELD_MASKED_REASON,
    FormFillInput,
    fill_form,
)
from butler_pc_core.dlp.runtime import scan_runtime as _scan_runtime
from butler_pc_core.runtime.json_grammar import GrammarUnavailable
from butler_pc_core.runtime import json_grammar


@pytest.fixture(autouse=True)
def _synthetic_grammar(monkeypatch: pytest.MonkeyPatch) -> None:
    if json_grammar.LlamaGrammar is None:
        monkeypatch.setattr(
            "butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar",
            lambda *_args, **_kwargs: object(),
        )


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


@pytest.mark.requires_llama_grammar
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


@pytest.mark.requires_llama_grammar
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


@pytest.mark.requires_llama_grammar
def test_fill_form_rejects_non_json_fail_closed() -> None:
    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient("양식 채우기가 완료되었습니다."),
    )

    assert result.filled_form == ""
    assert result.review_required == ["결과 형식 확인"]
    assert result.warnings == ["MODEL_JSON_NOT_FOUND"]


@pytest.mark.requires_llama_grammar
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


@pytest.mark.requires_llama_grammar
def test_fill_form_rejects_legacy_mapping_schema() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping["source_excerpt"] = "원문 일부"

    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload(field_mappings=[mapping])),
    )

    assert result.warnings == ["LEGACY_MAPPING_SCHEMA"]


@pytest.mark.requires_llama_grammar
def test_fill_form_rejects_top_level_extra_key() -> None:
    result = fill_form(
        FormFillInput(blank_form="법인명: ___", data_documents=[]),
        model_client=FakeModelClient(valid_payload(raw_response="원문")),
    )

    assert result.warnings == ["SCHEMA_KEYS_INVALID"]


@pytest.mark.requires_llama_grammar
def test_fill_form_masks_secret_label_real_value_without_review_markers() -> None:
    # A sensitive field with a real value and no review markers is now masked at
    # field level (not a whole-form abort): its value is replaced and the reason
    # recorded, while the rest of the form keeps processing.
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

    # No whole-form abort: the form is still produced and no block warning is set.
    assert result.filled_form != ""
    assert result.warnings != ["SENSITIVE_FIELD_AUTOFILL_BLOCKED"]
    # The sensitive field itself is masked with the explicit reason_code.
    assert result.field_mappings[0]["output_value"] == SAFE_SECRET_REPLACEMENT
    assert result.field_mappings[0]["reason_code"] == SENSITIVE_FIELD_MASKED_REASON
    # The real secret value never appears anywhere in the output.
    assert "plain-secret-1234" not in json.dumps(result.to_payload(), ensure_ascii=False)


@pytest.mark.requires_llama_grammar
def test_fill_form_mixed_form_masks_only_sensitive_fields_no_whole_form_block() -> None:
    # Mixed form: 6 general fields + 2 sensitive fields (both carrying real values
    # and no review markers, i.e. the case that previously aborted the ENTIRE form).
    # Expected new behavior: the 6 general fields fill normally, only the 2
    # sensitive fields are masked, and there is zero whole-form block.
    # General values are chosen to be non-PII so the DLP (#856) layer leaves them
    # intact — this test isolates the field-level sensitive-label masking, not DLP.
    general_fields = [
        {"target_label": "납품업체명", "output_value": "주식회사 버틀러", "source_ref": "our_data.회사명"},
        {"target_label": "대표이사", "output_value": "김대표", "source_ref": "our_data.대표"},
        {"target_label": "주소", "output_value": "서울시 강남구 테헤란로 1", "source_ref": "our_data.주소"},
        {"target_label": "담당부서", "output_value": "영업1팀", "source_ref": "our_data.부서"},
        {"target_label": "고용형태", "output_value": "정규직", "source_ref": "our_data.고용"},
        {"target_label": "등급", "output_value": "우수", "source_ref": "our_data.등급"},
    ]
    field_mappings = [
        {
            "target_label": g["target_label"],
            "output_value": g["output_value"],
            "confidence": "HIGH",
            "source_ref": g["source_ref"],
            "reason_code": "LABEL_SEMANTIC_MATCH",
        }
        for g in general_fields
    ]
    sensitive_fields = [
        {"target_label": "API 키", "output_value": "plain-secret-aaaa", "source_ref": "our_data.api_key"},
        {"target_label": "비밀번호", "output_value": "plain-secret-bbbb", "source_ref": "our_data.password"},
    ]
    field_mappings.extend(
        {
            "target_label": s["target_label"],
            "output_value": s["output_value"],
            "confidence": "HIGH",
            "source_ref": s["source_ref"],
            "reason_code": "LABEL_SEMANTIC_MATCH",
        }
        for s in sensitive_fields
    )

    result = fill_form(
        FormFillInput(
            blank_form="납품업체명: ___\nAPI 키: ___\n비밀번호: ___",
            data_documents=["회사명: 주식회사 버틀러"],
        ),
        model_client=FakeModelClient(
            valid_payload(
                filled_form="납품업체명: 주식회사 버틀러\n대표이사: 김대표",
                field_mappings=field_mappings,
                unfilled_fields=[],
                review_required=[],
                warnings=[],
            )
        ),
    )

    # Zero whole-form block: all 8 fields survive and the form is produced.
    assert result.filled_form != ""
    assert result.warnings != ["SENSITIVE_FIELD_AUTOFILL_BLOCKED"]
    assert len(result.field_mappings) == 8

    by_label = {m["target_label"]: m for m in result.field_mappings}

    # The 6 general fields keep their real values, untouched.
    for g in general_fields:
        assert by_label[g["target_label"]]["output_value"] == g["output_value"]
        assert by_label[g["target_label"]]["reason_code"] != SENSITIVE_FIELD_MASKED_REASON

    # The 2 sensitive fields are masked with the explicit reason_code.
    for s in sensitive_fields:
        assert by_label[s["target_label"]]["output_value"] == SAFE_SECRET_REPLACEMENT
        assert by_label[s["target_label"]]["reason_code"] == SENSITIVE_FIELD_MASKED_REASON

    # Gap ①: masked sensitive fields are auto-enrolled into review_required so the
    # frontend guard treats them as reviewed rather than blocking the whole form.
    for s in sensitive_fields:
        assert s["target_label"] in result.review_required

    # No sensitive value leaks anywhere in the returned payload.
    dumped = json.dumps(result.to_payload(), ensure_ascii=False)
    assert "plain-secret-aaaa" not in dumped
    assert "plain-secret-bbbb" not in dumped


@pytest.mark.requires_llama_grammar
def test_fill_form_mixed_filled_form_preserves_general_lines_and_masks_secret_lines() -> None:
    # Gap ③ real scenario: the secret real values live in filled_form itself
    # (6 general lines + 2 secret lines). The 1st-round test omitted this and so
    # dodged the whole-form filled_form collapse. Expected: general lines preserved
    # verbatim, secret lines shown only as the safe replacement, no raw leak.
    filled_form = (
        "납품업체명: 주식회사 버틀러\n"
        "대표이사: 김대표\n"
        "주소: 서울시 강남구 테헤란로 1\n"
        "담당부서: 영업1팀\n"
        "고용형태: 정규직\n"
        "등급: 우수\n"
        "API 키: plain-secret-aaaa\n"
        "비밀번호: plain-secret-bbbb"
    )
    general_lines = [
        "납품업체명: 주식회사 버틀러",
        "대표이사: 김대표",
        "주소: 서울시 강남구 테헤란로 1",
        "담당부서: 영업1팀",
        "고용형태: 정규직",
        "등급: 우수",
    ]
    field_mappings = [
        {
            "target_label": tl,
            "output_value": ov,
            "confidence": "HIGH",
            "source_ref": f"our_data.{i}",
            "reason_code": "LABEL_SEMANTIC_MATCH",
        }
        for i, (tl, ov) in enumerate(
            [
                ("납품업체명", "주식회사 버틀러"),
                ("대표이사", "김대표"),
                ("주소", "서울시 강남구 테헤란로 1"),
                ("담당부서", "영업1팀"),
                ("고용형태", "정규직"),
                ("등급", "우수"),
                ("API 키", "plain-secret-aaaa"),
                ("비밀번호", "plain-secret-bbbb"),
            ]
        )
    ]

    result = fill_form(
        FormFillInput(blank_form="납품업체명: ___\nAPI 키: ___\n비밀번호: ___", data_documents=[]),
        model_client=FakeModelClient(
            valid_payload(
                filled_form=filled_form,
                field_mappings=field_mappings,
                unfilled_fields=[],
                review_required=[],
                warnings=[],
            )
        ),
    )

    # 1) General 6 lines preserved verbatim in filled_form.
    for line in general_lines:
        assert line in result.filled_form
    # ... and the 2 secret lines appear only as the safe replacement (label gone).
    assert "API 키: " not in result.filled_form
    assert "비밀번호: " not in result.filled_form
    assert result.filled_form.count(SAFE_SECRET_REPLACEMENT) == 2

    # 2) field_mappings keeps all 8 entries (general kept, sensitive masked).
    assert len(result.field_mappings) == 8

    # 3) review_required includes the 2 sensitive fields.
    assert "API 키" in result.review_required
    assert "비밀번호" in result.review_required

    # 5) No raw secret anywhere — payload grep AND runtime DLP re-scan on filled_form.
    dumped = json.dumps(result.to_payload(), ensure_ascii=False)
    assert "plain-secret-aaaa" not in dumped
    assert "plain-secret-bbbb" not in dumped
    assert not _scan_runtime(result.filled_form).any_detected


@pytest.mark.requires_llama_grammar
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


@pytest.mark.requires_llama_grammar
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


@pytest.mark.requires_llama_grammar
def test_fill_form_redacts_secret_label_values_in_filled_form_and_warnings() -> None:
    mapping = dict(valid_payload()["field_mappings"][0])  # type: ignore[index]
    mapping.update(
        {
            "target_label": "API 키",
            "output_value": "UNFILLED",
            "confidence": "UNFILLED",
            "source_ref": "",
            "reason_code": "SENSITIVE_FIELD_REQUIRES_MANUAL_INPUT",
        }
    )

    result = fill_form(
        FormFillInput(blank_form="API 키: ___\nclient secret: ___", data_documents=[]),
        model_client=FakeModelClient(
            valid_payload(
                filled_form="API 키: plain-secret-1234\nclient secret: abcdef123456",
                field_mappings=[mapping],
                unfilled_fields=["API 키"],
                review_required=["API 키"],
                warnings=["seed phrase: correct horse battery staple 값은 수동 확인 필요"],
            )
        ),
    )

    dumped = json.dumps(result.to_payload(), ensure_ascii=False)
    assert result.warnings != ["SENSITIVE_FIELD_AUTOFILL_BLOCKED"]
    assert "plain-secret-1234" not in dumped
    assert "abcdef123456" not in dumped
    assert "correct horse battery staple" not in dumped
    # filled_form is rebuilt line-wise: both lines carry secret labels, so each
    # collapses to the safe replacement (no single wholesale collapse, no leak).
    assert result.filled_form.split("\n") == [SAFE_SECRET_REPLACEMENT, SAFE_SECRET_REPLACEMENT]
    assert dumped.count(SAFE_SECRET_REPLACEMENT) >= 2


def test_box6_json_schema_matches_backend_contract() -> None:
    assert set(BOX6_JSON_SCHEMA["required"]) == REQUIRED_TOP_LEVEL_KEYS
    mapping_schema = BOX6_JSON_SCHEMA["properties"]["field_mappings"]["items"]  # type: ignore[index]
    assert set(mapping_schema["required"]) == REQUIRED_MAPPING_KEYS
    assert BOX6_JSON_SCHEMA["properties"]["review_required"]["type"] == "array"  # type: ignore[index]
    assert set(mapping_schema["properties"]["confidence"]["enum"]) == CONFIDENCES  # type: ignore[index]
    assert BOX6_JSON_SCHEMA["additionalProperties"] is False
    assert mapping_schema["additionalProperties"] is False
