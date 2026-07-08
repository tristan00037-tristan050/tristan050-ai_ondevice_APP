from __future__ import annotations

import pytest

from butler_pc_core.cards.box4.review_service import BOX4_JSON_SCHEMA
from butler_pc_core.cards.box6.form_fill_service import BOX6_JSON_SCHEMA
from butler_pc_core.runtime.json_grammar import (
    FORBIDDEN_JSON_SCHEMA_KEYS,
    GrammarUnavailable,
    ModelResponseTextUnavailable,
    assert_supported_schema_subset,
    build_json_schema_grammar,
    normalize_model_response_to_text,
    stable_schema_digest,
    structured_generation_telemetry,
)


def test_json_schema_grammar_builds_for_box4_and_box6() -> None:
    assert build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True) is not None
    assert build_json_schema_grammar(BOX6_JSON_SCHEMA, required=True) is not None


def test_json_schema_grammar_does_not_reuse_stateful_object() -> None:
    first = build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)
    second = build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)

    assert first is not second


def test_unsupported_schema_keywords_fail_closed() -> None:
    with pytest.raises(GrammarUnavailable, match="UNSUPPORTED_JSON_SCHEMA_KEY"):
        build_json_schema_grammar(
            {
                "type": "object",
                "properties": {"schema_version": {"const": "card_04.document_review.v1"}},
            },
            required=True,
        )


def test_optional_grammar_returns_none_when_unavailable(monkeypatch) -> None:
    import butler_pc_core.runtime.json_grammar as json_grammar

    monkeypatch.setattr(json_grammar, "LlamaGrammar", None)
    assert build_json_schema_grammar(BOX4_JSON_SCHEMA, required=False) is None
    with pytest.raises(GrammarUnavailable):
        build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)


def test_fallback_uses_llama_from_json_schema_when_converter_helper_is_missing(monkeypatch) -> None:
    import butler_pc_core.runtime.json_grammar as json_grammar

    class DummyGrammar:
        calls: list[tuple[str, bool]] = []

        @classmethod
        def from_json_schema(cls, schema_json: str, *, verbose: bool = False):  # type: ignore[no-untyped-def]
            cls.calls.append((schema_json, verbose))
            return {"schema_json": schema_json, "verbose": verbose}

    monkeypatch.setattr(json_grammar, "json_schema_to_gbnf", None)
    monkeypatch.setattr(json_grammar, "LlamaGrammar", DummyGrammar)

    grammar = json_grammar.build_json_schema_grammar({"type": "object"}, required=True)

    assert grammar["verbose"] is False
    assert DummyGrammar.calls


def test_box_schemas_use_supported_subset_only() -> None:
    for schema in (BOX4_JSON_SCHEMA, BOX6_JSON_SCHEMA):
        assert_supported_schema_subset(schema)
        dumped = repr(schema)
        assert not any(keyword in dumped for keyword in FORBIDDEN_JSON_SCHEMA_KEYS)
        assert schema["additionalProperties"] is False


def test_stable_schema_digest_is_deterministic() -> None:
    assert stable_schema_digest(BOX4_JSON_SCHEMA) == stable_schema_digest(dict(reversed(list(BOX4_JSON_SCHEMA.items()))))


def test_normalize_completion_dict_text() -> None:
    assert normalize_model_response_to_text({"choices": [{"text": "{\"ok\": true}"}]}) == "{\"ok\": true}"


def test_normalize_chat_dict_message_content() -> None:
    assert normalize_model_response_to_text({"choices": [{"message": {"content": "{\"ok\": true}"}}]}) == "{\"ok\": true}"


def test_normalize_rejects_generator_and_unknown_types() -> None:
    def gen():
        yield {"choices": [{"text": "x"}]}

    with pytest.raises(ModelResponseTextUnavailable):
        normalize_model_response_to_text(gen())
    with pytest.raises(ModelResponseTextUnavailable):
        normalize_model_response_to_text({"unexpected": "value"})


def test_structured_generation_telemetry_is_raw_zero() -> None:
    meta = structured_generation_telemetry(
        '{"ok":true}',
        event="structured_generation",
        card_mode="4",
        schema_id="card_04.document_review.v1",
        schema_digest=stable_schema_digest(BOX4_JSON_SCHEMA),
        grammar_required=True,
        grammar_applied=True,
        method_selected="generate_with_cancel",
        model_client_class="Fake",
    )

    assert meta["response_len"] == len('{"ok":true}')
    assert meta["has_open_brace"] is True
    assert meta["has_close_brace"] is True
    assert meta["raw_text_logged"] is False
    assert "response_prefix" not in meta
    assert "prompt" not in meta
