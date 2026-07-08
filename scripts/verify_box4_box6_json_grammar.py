#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REQUIRED_FILES = [
    Path("butler_pc_core/runtime/json_grammar.py"),
    Path("butler_pc_core/runtime/llm_runtime.py"),
    Path("butler_pc_core/cards/box4/review_service.py"),
    Path("butler_pc_core/cards/box6/form_fill_service.py"),
]
FORBIDDEN_SCHEMA_KEYS = {
    "const",
    "$ref",
    "$defs",
    "definitions",
    "oneOf",
    "anyOf",
    "allOf",
    "patternProperties",
}


def fail(code: str) -> None:
    print("BOX4_BOX6_JSON_GRAMMAR_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def read(root: Path, rel: Path) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError:
        fail("SOURCE_FILE_MISSING")


def function_arg_names(tree: ast.Module, name: str) -> list[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "LlmRuntime":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return [arg.arg for arg in child.args.args]
    return []


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            fail("REQUIRED_FILE_MISSING")

    grammar = read(root, Path("butler_pc_core/runtime/json_grammar.py"))
    runtime = read(root, Path("butler_pc_core/runtime/llm_runtime.py"))
    box4 = read(root, Path("butler_pc_core/cards/box4/review_service.py"))
    box6 = read(root, Path("butler_pc_core/cards/box6/form_fill_service.py"))

    if "LlamaGrammar.from_json_schema" not in grammar:
        fail("FROM_JSON_SCHEMA_MISSING")
    if "required: bool" not in grammar or "GrammarUnavailable" not in grammar:
        fail("GRAMMAR_REQUIRED_FAIL_CLOSED_MISSING")
    if "@lru_cache(maxsize=16)" not in grammar:
        fail("GRAMMAR_CACHE_MISSING")
    if "FORBIDDEN_JSON_SCHEMA_KEYS" not in grammar:
        fail("SUBSET_GUARD_MISSING")

    runtime_tree = ast.parse(runtime)
    for function_name in ("generate", "generate_stream", "generate_with_cancel", "generate_stream_with_cancel"):
        if "grammar" not in function_arg_names(runtime_tree, function_name):
            fail(f"RUNTIME_GRAMMAR_ARG_MISSING:{function_name}")
    if 'call_kwargs["grammar"] = grammar' not in runtime:
        fail("GRAMMAR_KWARG_NOT_CONDITIONAL")
    grammar_block = runtime[runtime.find('if grammar is not None:') : runtime.find('return call_kwargs')]
    if 'call_kwargs["temperature"] = 0.1' not in grammar_block or 'call_kwargs.setdefault("top_p", 0.95)' not in grammar_block:
        fail("STRUCTURED_TEMPERATURE_BLOCK_MISSING")

    for source, box_name in ((box4, "BOX4"), (box6, "BOX6")):
        if f"{box_name}_JSON_SCHEMA" not in source:
            fail(f"{box_name}_SCHEMA_MISSING")
        if "build_json_schema_grammar" not in source or "required=True" not in source:
            fail(f"{box_name}_REQUIRED_GRAMMAR_MISSING")
        if "GRAMMAR_UNAVAILABLE" not in source:
            fail(f"{box_name}_GRAMMAR_FAIL_CLOSED_MISSING")
        if "_validate_" not in source or "_require_exact_keys" not in source:
            fail(f"{box_name}_VALIDATOR_REMOVED")
        if "normalize_model_response_to_text" not in source:
            fail(f"{box_name}_NORMALIZER_MISSING")
        schema_region = source[source.find(f"{box_name}_JSON_SCHEMA") : source.find(f"{box_name}_SCHEMA_DIGEST")]
        for key in FORBIDDEN_SCHEMA_KEYS:
            if key in schema_region:
                fail(f"{box_name}_FORBIDDEN_SCHEMA_KEY:{key}")
        if '"additionalProperties": False' not in schema_region:
            fail(f"{box_name}_ADDITIONAL_PROPERTIES_MISSING")

    if "generate_text(prompt" in box4 + box6:
        fail("STRUCTURED_GENERATE_TEXT_FORBIDDEN")
    if "str(value)" in box4[box4.find("normalize_model_response_to_text") : box4.find("def _require_string")]:
        fail("BOX4_STR_DICT_FALLBACK_RISK")
    if "str(value)" in box6[box6.find("normalize_model_response_to_text") : box6.find("def _require_string")]:
        fail("BOX6_STR_DICT_FALLBACK_RISK")
    for forbidden in ("prompt[:", "response[:", "model_output[:", "print(model_output", "print(prompt"):
        if forbidden in box4 + box6 + runtime:
            fail("RAW_PREFIX_LOGGING_FORBIDDEN")

    print("BOX4_BOX6_JSON_GRAMMAR_OK=1")
    print("FROM_JSON_SCHEMA_USED=1")
    print("BOX4_GRAMMAR_REQUIRED=1")
    print("BOX6_GRAMMAR_REQUIRED=1")
    print("GRAMMAR_NONE_LEGACY_KWARG_GUARD=1")
    print("VALIDATOR_SECOND_LINE_DEFENSE=1")
    print("RAW_PREFIX_LOGGING=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
