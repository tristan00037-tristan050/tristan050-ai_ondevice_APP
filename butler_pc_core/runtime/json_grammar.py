"""JSON Schema grammar helpers for structured local LLM calls."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from types import GeneratorType
from typing import Any, Mapping

try:
    from llama_cpp import LlamaGrammar  # type: ignore[import]
except Exception:  # pragma: no cover - exercised in environments without llama-cpp
    LlamaGrammar = None  # type: ignore[assignment]

try:
    from llama_cpp.llama_grammar import json_schema_to_gbnf  # type: ignore[import]
except Exception:  # pragma: no cover - exercised by llama-cpp builds without the helper module
    json_schema_to_gbnf = None  # type: ignore[assignment]


FORBIDDEN_JSON_SCHEMA_KEYS = frozenset(
    {
        "$ref",
        "$defs",
        "definitions",
        "oneOf",
        "anyOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "dependentSchemas",
        "patternProperties",
        "uniqueItems",
        "contains",
        "minContains",
        "const",
    }
)


class GrammarUnavailable(RuntimeError):
    """Raised when a required JSON grammar cannot be built safely."""


class ModelResponseTextUnavailable(ValueError):
    """Raised when a model response cannot be normalized without raw fallback."""


def stable_json_dumps(obj: Mapping[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_schema_digest(schema: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(stable_json_dumps(schema).encode("utf-8")).hexdigest()


def assert_supported_schema_subset(schema: Any, path: str = "$") -> None:
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in FORBIDDEN_JSON_SCHEMA_KEYS:
                raise GrammarUnavailable(f"UNSUPPORTED_JSON_SCHEMA_KEY:{path}.{key}")
            assert_supported_schema_subset(value, f"{path}.{key}")
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            assert_supported_schema_subset(value, f"{path}[{index}]")


@lru_cache(maxsize=16)
def _schema_json_to_gbnf_cached(schema_json: str) -> str:
    if json_schema_to_gbnf is None:
        raise GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")
    try:
        return str(json_schema_to_gbnf(schema_json))
    except Exception as exc:  # noqa: BLE001
        raise GrammarUnavailable("LLAMA_GRAMMAR_BUILD_FAILED") from exc


def _from_string(grammar_text: str):
    if LlamaGrammar is None:
        raise GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")
    try:
        return LlamaGrammar.from_string(grammar_text, verbose=False)
    except TypeError:
        return LlamaGrammar.from_string(grammar_text)
    except Exception as exc:  # noqa: BLE001
        raise GrammarUnavailable("LLAMA_GRAMMAR_BUILD_FAILED") from exc


def build_json_schema_grammar(schema: Mapping[str, Any], *, required: bool):
    try:
        assert_supported_schema_subset(schema)
        schema_json = stable_json_dumps(schema)
        if json_schema_to_gbnf is not None:
            return _from_string(_schema_json_to_gbnf_cached(schema_json))
        if LlamaGrammar is None:
            raise GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")
        try:
            return LlamaGrammar.from_json_schema(schema_json, verbose=False)
        except TypeError:
            return LlamaGrammar.from_json_schema(schema_json)
        except Exception as exc:  # noqa: BLE001
            raise GrammarUnavailable("LLAMA_GRAMMAR_BUILD_FAILED") from exc
    except GrammarUnavailable:
        if required:
            raise
        return None


def normalize_model_response_to_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, GeneratorType) or hasattr(response, "__next__"):
        raise ModelResponseTextUnavailable("MODEL_RESPONSE_GENERATOR_UNSUPPORTED")
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    return text
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return str(message["content"])
                delta = first.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    return str(delta["content"])
        raise ModelResponseTextUnavailable("MODEL_RESPONSE_TEXT_UNAVAILABLE")
    raise ModelResponseTextUnavailable("MODEL_RESPONSE_TYPE_UNSUPPORTED")


def structured_generation_telemetry(
    response_text: str,
    *,
    event: str,
    card_mode: str,
    schema_id: str,
    schema_digest: str,
    grammar_required: bool,
    grammar_applied: bool,
    method_selected: str,
    model_client_class: str,
    reason_code: str = "",
) -> dict[str, object]:
    return {
        "event": event,
        "card_mode": card_mode,
        "schema_id": schema_id,
        "schema_digest": schema_digest,
        "grammar_required": grammar_required,
        "grammar_applied": grammar_applied,
        "method_selected": method_selected,
        "model_client_class": model_client_class,
        "response_len": len(response_text),
        "response_sha256": "sha256:" + hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
        "has_open_brace": "{" in response_text,
        "has_close_brace": "}" in response_text,
        "reason_code": reason_code,
        "raw_text_logged": False,
        "external_send_zero": True,
    }
