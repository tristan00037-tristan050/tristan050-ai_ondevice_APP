#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


REVIEW_SERVICE = Path("butler_pc_core/cards/box4/review_service.py")
BOX4_PROMPT = Path("butler_pc_core/prompts/cards/card_04_document_review.yaml")
CARD_RENDERER = Path("butler_pc_core/prompts/card_renderer.py")
CARD_GRID = Path("butler-desktop/src/components/v1_1/CardGrid.tsx")
SIDECAR = Path("butler_sidecar.py")
TEST_FILES = (
    Path("tests/prompts/test_card04_document_review.py"),
    Path("tests/cards/box4/test_review_service.py"),
    Path("butler-desktop/src/__tests__/Box4CardMode.test.tsx"),
)
DEPENDENCY_FILE_RE = re.compile(
    r"(^|/)(package(-lock)?\.json|pyproject\.toml|requirements[^/]*\.txt|poetry\.lock|uv\.lock)$"
)
SUCCESS_MARKER_RE = re.compile(r"\b[A-Z0-9_]+_OK=1\b")
FORBIDDEN_SEND_IMPORTS = {"requests", "httpx", "aiohttp", "urllib", "socket"}
ISSUE_TYPES = {"MISSING", "ERROR", "INCONSISTENCY", "STYLE", "SUGGESTION"}
CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}


def _fail(code: str) -> None:
    print("BOX4_DOCUMENT_REVIEW_CONTRACT_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _read(root: Path, rel: Path) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError:
        _fail("SOURCE_FILE_MISSING")


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError:
        _fail("SOURCE_PARSE_ERROR")


def _changed_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        _fail("GIT_UNAVAILABLE")
    if result.returncode != 0:
        _fail("GIT_DIFF_FAILED")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _check_review_service(root: Path) -> None:
    source = _read(root, REVIEW_SERVICE)
    tree = _parse(source)
    names = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    required = {
        "DocumentReviewInput",
        "DocumentReviewResult",
        "review_document",
        "_extract_json_object",
        "_validate_review_payload",
        "_safe_error_result",
    }
    if not required.issubset(names):
        _fail("REVIEW_SERVICE_API_MISSING")
    if "card_04.document_review.v1" not in source:
        _fail("SCHEMA_VERSION_MISSING")
    if "ast.literal_eval" in source or re.search(r"\beval\s*\(", source):
        _fail("UNSAFE_JSON_PARSER_PRESENT")
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    if imports & FORBIDDEN_SEND_IMPORTS:
        _fail("EXTERNAL_SEND_IMPORT_PRESENT")
    for value in ISSUE_TYPES | CONFIDENCES:
        if value not in source:
            _fail("ENUM_VALUE_MISSING")


def _check_prompt(root: Path) -> None:
    source = _read(root, BOX4_PROMPT)
    required = (
        "card_04.document_review.v1",
        "issue_type",
        "original_text",
        "suggestion",
        "confidence",
        "신뢰할 수 없는 데이터",
        "오류 없다고 보고하라",
        "이전 지시를 무시하라",
        "민감정보 원문",
        "JSON 객체 하나만",
    )
    for needle in required:
        if needle not in source:
            _fail("PROMPT_CONTRACT_MISSING")


def _check_wiring(root: Path) -> None:
    sidecar = _read(root, SIDECAR)
    if "review_document" not in sidecar or 'normalize_card_mode(params.card_mode) == "4"' not in sidecar:
        _fail("SIDECAR_CARD4_WIRING_MISSING")
    if "CompanyKnowledgeResolver" not in sidecar:
        _fail("SIDECAR_BASELINE_DRIFT")


def _check_card_grid(root: Path) -> None:
    source = _read(root, CARD_GRID)
    if "BOX4_DOCUMENT_REVIEW_ENABLED" not in source:
        _fail("BOX4_FLAG_MISSING")
    if "VITE_BUTLER_BOX4_DOCUMENT_REVIEW" not in source or "=== '1'" not in source:
        _fail("BOX4_FLAG_NOT_STRICT")
    card4_segment = re.search(r"\{\s*id:\s*4,.*?\}", source, re.DOTALL)
    if not card4_segment:
        _fail("BOX4_CARD_MISSING")
    segment = card4_segment.group(0)
    if "active: BOX4_DOCUMENT_REVIEW_ENABLED" not in segment:
        _fail("BOX4_FLAG_DEFAULT_OFF_MISSING")
    if "active: true" in segment:
        _fail("BOX4_ACTIVE_TRUE_FORBIDDEN")


def _check_renderer(root: Path) -> None:
    source = _read(root, CARD_RENDERER)
    if "json.dumps_kwargs" in source or ".policies[" in source:
        _fail("CARD_RENDERER_GLOBAL_ENV_MUTATION_RISK")


def _check_tests(root: Path) -> None:
    for rel in TEST_FILES:
        if not (root / rel).is_file():
            _fail("TEST_FILE_MISSING")
        source = _read(root, rel)
        if SUCCESS_MARKER_RE.search(source):
            _fail("TEST_SUCCESS_MARKER_CONTAMINATION")


def _check_dependency_files_unchanged(root: Path) -> None:
    for changed in _changed_files(root):
        if DEPENDENCY_FILE_RE.search(changed):
            _fail("DEPENDENCY_FILE_CHANGED")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    _check_review_service(root)
    _check_prompt(root)
    _check_wiring(root)
    _check_card_grid(root)
    _check_renderer(root)
    _check_tests(root)
    _check_dependency_files_unchanged(root)
    print("BOX4_DOCUMENT_REVIEW_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
