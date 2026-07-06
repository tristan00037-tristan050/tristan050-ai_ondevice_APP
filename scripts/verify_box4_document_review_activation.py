#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

REQUIRED_ENUMS = {"MISSING", "ERROR", "INCONSISTENCY", "STYLE", "SUGGESTION"}
FORBIDDEN_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "socket"}
FORBIDDEN_PARSE_CALLS = {"eval", "literal_eval"}


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def _call_names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                found.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                found.add(fn.attr)
    return found


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    service = root / "butler_pc_core/cards/box4/review_service.py"
    card_grid = root / "butler-desktop/src/components/v1_1/CardGrid.tsx"
    tests = root / "tests/cards/box4/test_review_service.py"
    failures: list[str] = []
    if not service.exists():
        failures.append("REVIEW_SERVICE_MISSING")
    if not card_grid.exists():
        failures.append("CARDGRID_MISSING")
    if not tests.exists():
        failures.append("BOX4_TESTS_MISSING")
    if not failures:
        source = service.read_text(encoding="utf-8")
        tree = ast.parse(source)
        if "card_04.document_review.v1" not in source:
            failures.append("SCHEMA_VERSION_MISSING")
        for enum_value in REQUIRED_ENUMS:
            if enum_value not in source:
                failures.append(f"ENUM_MISSING:{enum_value}")
        bad_imports = _imports(tree) & FORBIDDEN_IMPORTS
        if bad_imports:
            failures.append("EXTERNAL_SEND_IMPORT_FORBIDDEN")
        bad_calls = _call_names(tree) & FORBIDDEN_PARSE_CALLS
        if bad_calls:
            failures.append("UNSAFE_PARSE_CALL_FORBIDDEN")
        for required in ("_extract_json_object", "_validate_review_payload", "_safe_error_result"):
            if required not in source:
                failures.append(f"REQUIRED_FUNCTION_MISSING:{required}")
        grid = card_grid.read_text(encoding="utf-8")
        if "VITE_BUTLER_BOX4_DOCUMENT_REVIEW" not in grid:
            failures.append("BOX4_FLAG_MISSING")
        if "active: true" in grid and "id: 4" in grid:
            failures.append("BOX4_ACTIVE_TRUE_FORBIDDEN")
    if failures:
        print("BOX4_DOCUMENT_REVIEW_CONTRACT_OK=0")
        for failure in failures:
            print("FAIL=" + failure)
        return 1
    print("BOX4_DOCUMENT_REVIEW_CONTRACT_OK=1")
    print("review_service=present")
    print("json_fail_closed=present")
    print("external_send_imports=0")
    print("box4_flag_default_off=present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
