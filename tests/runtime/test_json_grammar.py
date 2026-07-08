from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from butler_pc_core.cards.box4.review_service import BOX4_JSON_SCHEMA, DocumentReviewInput, review_document
from butler_pc_core.cards.box6.form_fill_service import BOX6_JSON_SCHEMA, FormFillInput, fill_form
from butler_pc_core.runtime import llm_runtime
from butler_pc_core.runtime.json_grammar import (
    GrammarUnavailable,
    assert_supported_schema_subset,
    build_json_schema_grammar,
    stable_schema_digest,
)


class FakeGrammarModel:
    def __init__(self, text: str):
        self.text = text
        self.kwargs: dict[str, object] = {}

    def generate_with_cancel(self, prompt: str, cancel_event: threading.Event, **kwargs):
        self.kwargs = dict(kwargs)
        return self.text


class FakeGenerateOnlyModel:
    def __init__(self, text: str):
        self.text = text
        self.kwargs: dict[str, object] = {}

    def generate(self, prompt: str, **kwargs):
        self.kwargs = dict(kwargs)
        return self.text


def test_supported_schema_subset_accepts_box4_box6_and_rejects_const():
    assert_supported_schema_subset(BOX4_JSON_SCHEMA)
    assert_supported_schema_subset(BOX6_JSON_SCHEMA)
    with pytest.raises(GrammarUnavailable):
        assert_supported_schema_subset({"type": "object", "properties": {"x": {"const": "y"}}})


def test_optional_grammar_returns_none_when_import_unavailable(monkeypatch):
    monkeypatch.setattr("butler_pc_core.runtime.json_grammar.LlamaGrammar", None)
    assert build_json_schema_grammar(BOX4_JSON_SCHEMA, required=False) is None
    with pytest.raises(GrammarUnavailable):
        build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)


def test_schema_digest_is_stable_and_digest_safe():
    assert stable_schema_digest(BOX4_JSON_SCHEMA).startswith("sha256:")
    assert stable_schema_digest(BOX4_JSON_SCHEMA) == stable_schema_digest(dict(BOX4_JSON_SCHEMA))


def test_llm_runtime_grammar_kwargs_only_when_supplied():
    class FakeLlama:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def __call__(self, prompt: str, **kwargs):
            self.calls.append(kwargs)
            return {"choices": [{"text": "{}"}]}

        def reset(self):
            return None

    runtime = llm_runtime.LlmRuntime()
    runtime._status = "ready"
    runtime._llm = FakeLlama()
    runtime.generate("prompt")
    assert "grammar" not in runtime._llm.calls[-1]
    assert runtime._llm.calls[-1]["temperature"] == 0.2

    grammar = object()
    runtime.generate("prompt", grammar=grammar)
    assert runtime._llm.calls[-1]["grammar"] is grammar
    assert runtime._llm.calls[-1]["temperature"] == 0.1
    assert runtime._llm.calls[-1]["top_p"] == 0.95


def test_generate_with_cancel_receives_grammar(monkeypatch):
    class FakeLlama:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] = {}

        def __call__(self, prompt: str, **kwargs) -> Iterator[dict]:
            self.kwargs = kwargs
            yield {"choices": [{"text": "{}"}]}

    runtime = llm_runtime.LlmRuntime()
    runtime._status = "ready"
    runtime._llm = FakeLlama()
    grammar = object()
    assert runtime.generate_with_cancel("prompt", threading.Event(), grammar=grammar) == "{}"
    assert runtime._llm.kwargs["grammar"] is grammar


def test_box4_required_grammar_fail_closed(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box4.review_service.build_json_schema_grammar", lambda *a, **k: (_ for _ in ()).throw(GrammarUnavailable("x")))
    result = review_document(DocumentReviewInput("검토 문서", []), model_client=FakeGrammarModel("{}"))
    assert result.review_required is True
    assert result.warnings == ["GRAMMAR_UNAVAILABLE"]


def test_box4_valid_payload_uses_grammar(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box4.review_service.build_json_schema_grammar", lambda *a, **k: object())
    payload = '{"schema_version":"card_04.document_review.v1","issues":[],"overall_score":100,"summary":"문제 없음","review_required":false,"warnings":[]}'
    model = FakeGrammarModel(payload)
    result = review_document(DocumentReviewInput("문서", []), model_client=model)
    assert result.overall_score == 100
    assert "grammar" in model.kwargs


def test_box4_extra_key_and_missing_key_rejected(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box4.review_service.build_json_schema_grammar", lambda *a, **k: object())
    extra = '{"schema_version":"card_04.document_review.v1","issues":[],"overall_score":100,"summary":"문제 없음","review_required":false,"warnings":[],"extra":1}'
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeGrammarModel(extra))
    assert result.warnings == ["SCHEMA_KEYS_INVALID"]

    missing = '{"schema_version":"card_04.document_review.v1","issues":[],"overall_score":100,"summary":"문제 없음","review_required":false}'
    result = review_document(DocumentReviewInput("문서", []), model_client=FakeGrammarModel(missing))
    assert result.warnings == ["SCHEMA_KEYS_INVALID"]


def test_box6_required_grammar_fail_closed(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", lambda *a, **k: (_ for _ in ()).throw(GrammarUnavailable("x")))
    result = fill_form(FormFillInput("상호: ___", []), model_client=FakeGrammarModel("{}"))
    assert result.warnings == ["GRAMMAR_UNAVAILABLE"]


def test_box6_valid_payload_uses_grammar(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", lambda *a, **k: object())
    payload = '{"schema_version":"card_06.form_fill.v1","filled_form":"상호: 합성회사","field_mappings":[{"target_label":"상호","output_value":"합성회사","confidence":"HIGH","source_ref":"our_data.company_name","reason_code":"LABEL_EXACT_MATCH"}],"unfilled_fields":[],"review_required":[],"warnings":[]}'
    model = FakeGrammarModel(payload)
    result = fill_form(FormFillInput("상호: ___", ["상호: 합성회사"]), model_client=model)
    assert result.filled_form == "상호: 합성회사"
    assert "grammar" in model.kwargs


def test_box6_legacy_source_excerpt_and_mapping_review_required_rejected(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", lambda *a, **k: object())
    payload = '{"schema_version":"card_06.form_fill.v1","filled_form":"","field_mappings":[{"target_label":"상호","output_value":"합성회사","confidence":"HIGH","source_ref":"x","reason_code":"x","source_excerpt":"legacy"}],"unfilled_fields":[],"review_required":[],"warnings":[]}'
    result = fill_form(FormFillInput("상호: ___", ["상호: 합성회사"]), model_client=FakeGrammarModel(payload))
    assert result.warnings == ["FIELD_MAPPING_KEYS_INVALID"]


def test_box6_secret_autofill_rejected(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", lambda *a, **k: object())
    payload = '{"schema_version":"card_06.form_fill.v1","filled_form":"API Key: [민감정보 원문 생략]","field_mappings":[{"target_label":"API Key","output_value":"값 있음","confidence":"HIGH","source_ref":"x","reason_code":"x"}],"unfilled_fields":[],"review_required":[],"warnings":[]}'
    result = fill_form(FormFillInput("API Key: ___", ["API Key: abc"]), model_client=FakeGrammarModel(payload))
    assert result.warnings == ["SECRET_AUTOFILL_FORBIDDEN"]


def test_box6_secret_label_unfilled_listed_for_review_allowed(monkeypatch):
    monkeypatch.setattr("butler_pc_core.cards.box6.form_fill_service.build_json_schema_grammar", lambda *a, **k: object())
    payload = '{"schema_version":"card_06.form_fill.v1","filled_form":"API Key: [확인 필요]","field_mappings":[{"target_label":"API Key","output_value":"[확인 필요]","confidence":"UNFILLED","source_ref":"","reason_code":"FORBIDDEN_SECRET_FIELD"}],"unfilled_fields":["API Key"],"review_required":["API Key"],"warnings":[]}'
    result = fill_form(FormFillInput("API Key: ___", []), model_client=FakeGrammarModel(payload))
    assert result.review_required == ["API Key"]


def test_generate_text_fallback_is_not_used_in_structured_services(monkeypatch):
    class GenerateTextOnly:
        def generate_text(self, *args, **kwargs):
            return "{}"

    monkeypatch.setattr("butler_pc_core.cards.box4.review_service.build_json_schema_grammar", lambda *a, **k: object())
    result = review_document(DocumentReviewInput("문서", []), model_client=GenerateTextOnly())
    assert result.warnings == ["GRAMMAR_UNAVAILABLE"]
