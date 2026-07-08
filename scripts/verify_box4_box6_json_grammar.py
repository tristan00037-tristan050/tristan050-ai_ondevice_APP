#!/usr/bin/env python3
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any


FORBIDDEN = {
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


def fail(code: str) -> int:
    print(f"BOX4_BOX6_JSON_GRAMMAR_OK=0 ERROR_CODE={code}")
    return 1


def walk_schema(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            items.append((str(key), child))
            items.extend(walk_schema(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(walk_schema(child))
    return items


def require_additional_properties_false(schema: dict[str, Any]) -> bool:
    if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
        return False
    for _, child in walk_schema(schema):
        if isinstance(child, dict) and child.get("type") == "object" and child.get("additionalProperties") is not False:
            return False
    return True


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    try:
        from llama_cpp import LlamaGrammar
    except Exception:
        return fail("LLAMA_GRAMMAR_IMPORT_FAILED")
    if not hasattr(LlamaGrammar, "from_json_schema"):
        return fail("FROM_JSON_SCHEMA_MISSING")

    from butler_pc_core.cards.box4.review_service import BOX4_JSON_SCHEMA
    from butler_pc_core.cards.box6.form_fill_service import BOX6_JSON_SCHEMA
    from butler_pc_core.inference.llm_runtime import LlmRuntime

    for name, schema in (("BOX4", BOX4_JSON_SCHEMA), ("BOX6", BOX6_JSON_SCHEMA)):
        if not require_additional_properties_false(schema):
            return fail(f"{name}_ADDITIONAL_PROPERTIES_NOT_FALSE")
        keys = {key for key, _ in walk_schema(schema)}
        if keys & FORBIDDEN:
            return fail(f"{name}_FORBIDDEN_SCHEMA_KEY")

    for method_name in ("generate", "generate_stream", "generate_with_cancel", "generate_stream_with_cancel"):
        sig = inspect.signature(getattr(LlmRuntime, method_name))
        param = sig.parameters.get("grammar")
        if param is None or param.default is not None:
            return fail(f"{method_name.upper()}_GRAMMAR_SIGNATURE_INVALID")

    box4_source = (repo / "butler_pc_core/cards/box4/review_service.py").read_text(encoding="utf-8")
    box6_source = (repo / "butler_pc_core/cards/box6/form_fill_service.py").read_text(encoding="utf-8")
    runtime_source = (repo / "butler_pc_core/inference/llm_runtime.py").read_text(encoding="utf-8")
    sidecar_source = (repo / "butler_sidecar.py").read_text(encoding="utf-8")

    if "build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)" not in box4_source:
        return fail("BOX4_REQUIRED_TRUE_MISSING")
    if "build_json_schema_grammar(BOX6_JSON_SCHEMA, required=True)" not in box6_source:
        return fail("BOX6_REQUIRED_TRUE_MISSING")
    if "GRAMMAR_UNAVAILABLE" not in box4_source or "GRAMMAR_UNAVAILABLE" not in box6_source:
        return fail("GRAMMAR_FAIL_CLOSED_MISSING")
    if "_require_exact_keys" not in box4_source or "_require_exact_keys" not in box6_source:
        return fail("VALIDATOR_EXACT_KEYS_MISSING")
    if "if grammar is not None:" not in runtime_source or 'call_kwargs["grammar"] = grammar' not in runtime_source:
        return fail("GRAMMAR_KWARGS_GUARD_MISSING")
    if '"source": "box6_form_fill"' not in sidecar_source:
        return fail("BOX6_STRUCTURED_ROUTE_MISSING")

    disallowed_refs = []
    for path in repo.rglob("*.py"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "build_json_schema_grammar(" not in text:
            continue
        rel = path.relative_to(repo).as_posix()
        if rel not in {
            "butler_pc_core/cards/box4/review_service.py",
            "butler_pc_core/cards/box6/form_fill_service.py",
            "butler_pc_core/runtime/json_grammar.py",
            "tests/runtime/test_json_grammar.py",
            "tests/cards/box4/test_review_service.py",
            "tests/cards/box6/test_form_fill_service.py",
            "scripts/verify_box4_box6_json_grammar.py",
        }:
            disallowed_refs.append(rel)
    if disallowed_refs:
        return fail("UNEXPECTED_GRAMMAR_CALLSITE")

    banned_raw_markers = ("response_prefix", "response_preview", "raw_response_prefix")
    for source in (box4_source, box6_source, runtime_source, sidecar_source):
        if any(marker in source for marker in banned_raw_markers):
            return fail("RAW_PREFIX_LOGGING_PRESENT")

    print("BOX4_BOX6_JSON_GRAMMAR_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
