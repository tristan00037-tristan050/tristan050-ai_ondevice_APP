from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any, Mapping

try:
    from llama_cpp import LlamaGrammar  # type: ignore[import]
except Exception:  # pragma: no cover - exercised in bundle/runtime capability checks
    LlamaGrammar = None  # type: ignore[assignment]

FORBIDDEN_JSON_SCHEMA_KEYS = {
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


class GrammarUnavailable(RuntimeError):
    """Raised when a required structured-output grammar cannot be built."""


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
def _build_grammar_cached(schema_json: str):
    if LlamaGrammar is None:
        raise GrammarUnavailable("LLAMA_GRAMMAR_IMPORT_FAILED")
    try:
        return LlamaGrammar.from_json_schema(schema_json, verbose=False)
    except TypeError:
        return LlamaGrammar.from_json_schema(schema_json)
    except Exception as exc:  # noqa: BLE001
        raise GrammarUnavailable("LLAMA_GRAMMAR_BUILD_FAILED") from exc


def build_json_schema_grammar(schema: Mapping[str, Any], *, required: bool):
    try:
        assert_supported_schema_subset(schema)
        return _build_grammar_cached(stable_json_dumps(schema))
    except GrammarUnavailable:
        if required:
            raise
        return None
