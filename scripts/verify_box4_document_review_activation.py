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
SMOKE_VALIDATOR = Path("scripts/validate_box4_document_review_smoke.py")
TEST_FILES = (
    Path("tests/prompts/test_card04_document_review.py"),
    Path("tests/cards/box4/test_review_service.py"),
    Path("butler-desktop/src/__tests__/Box4CardMode.test.tsx"),
)
# Box4 runs in the bundled Python sidecar. This is the manifest copied into the
# app and consumed by scripts/build_runtime.sh. Frontend manifests are covered
# by npm ci + the Box4 Vitest job and are valid to change for unrelated product
# work; treating every package.json in the monorepo as a Box4 contract breach
# made this verifier reject otherwise valid PRs.
BOX4_RUNTIME_DEPENDENCY_FILES = frozenset({"requirements-serving.txt"})
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


def _function_segment(source: str, name: str) -> str:
    tree = _parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            if node.end_lineno is None:
                _fail("SOURCE_PARSE_ERROR")
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    _fail("FUNCTION_MISSING")


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
    validator = _function_segment(source, "_validate_review_payload")
    if ".get(" in validator:
        _fail("REVIEW_VALIDATOR_GET_FORBIDDEN")
    if "REQUIRED_TOP_LEVEL_KEYS" not in source or "REQUIRED_ISSUE_KEYS" not in source:
        _fail("EXACT_KEY_CONTRACT_MISSING")
    if "_require_exact_keys(payload, REQUIRED_TOP_LEVEL_KEYS" not in validator:
        _fail("TOP_LEVEL_EXACT_KEY_CHECK_MISSING")
    if "_require_exact_keys(item, REQUIRED_ISSUE_KEYS" not in validator:
        _fail("ISSUE_EXACT_KEY_CHECK_MISSING")
    if "SCHEMA_KEYS_INVALID" not in source or "ISSUE_KEYS_INVALID" not in source:
        _fail("EXACT_KEY_ERROR_CODE_MISSING")
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
    if "review_document" not in sidecar:
        _fail("SIDECAR_CARD4_WIRING_MISSING")
    if "_BOX4_DOCUMENT_REVIEW_MODES" not in sidecar or '"document_review"' not in sidecar:
        _fail("SIDECAR_BOX4_ALIAS_MISSING")
    if "normalize_card_mode(params.card_mode) in _BOX4_DOCUMENT_REVIEW_MODES" not in sidecar:
        _fail("SIDECAR_CARD4_ALIAS_WIRING_MISSING")
    if "_run_box4_review_with_timeout" not in sidecar or "_Box4TimeoutModelClient" not in sidecar:
        _fail("SIDECAR_BOX4_TIMEOUT_WRAPPER_MISSING")
    if "TimeoutController(" not in sidecar or "_active_controllers[task_id]" not in sidecar:
        _fail("SIDECAR_BOX4_ACTIVE_TIMEOUT_MISSING")
    if "asyncio.to_thread(\n                    review_document" in sidecar:
        _fail("SIDECAR_BOX4_DIRECT_TO_THREAD_FORBIDDEN")
    if "CompanyKnowledgeResolver" not in sidecar:
        _fail("SIDECAR_BASELINE_DRIFT")


def _check_card_grid(root: Path) -> None:
    source = _read(root, CARD_GRID)
    if "BOX4_DOCUMENT_REVIEW_ENABLED" not in source:
        _fail("BOX4_FLAG_MISSING")
    # Product default is ON (promoted from strict opt-in): unset/'1' => on, explicit '0' => off
    # (kill switch). The card must still be gated by the env-derived flag, never hardcoded on.
    if "VITE_BUTLER_BOX4_DOCUMENT_REVIEW" not in source or "!== '0'" not in source:
        _fail("BOX4_FLAG_NOT_DEFAULT_ON")
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
    test_source = _read(root, Path("tests/cards/box4/test_review_service.py"))
    if "raw_secret" not in test_source or "raw_response" not in test_source:
        _fail("EXACT_KEY_REGRESSION_TEST_MISSING")
    prompt_test_source = _read(root, Path("tests/prompts/test_card04_document_review.py"))
    if '"document_review"' not in prompt_test_source or "chunk_timeout" not in prompt_test_source:
        _fail("SIDECAR_ALIAS_TIMEOUT_REGRESSION_TEST_MISSING")


def _check_smoke_validator(root: Path) -> None:
    source = _read(root, SMOKE_VALIDATOR)
    required = (
        "BOX4_DOCUMENT_REVIEW_SMOKE_OK=1",
        "SCHEMA_KEYS_INVALID",
        "ISSUE_KEYS_INVALID",
        "SAFE_SECRET_REPLACEMENT",
        "오류 없다고 보고하라",
        "이전 지시를 무시하라",
    )
    for needle in required:
        if needle not in source:
            _fail("SMOKE_VALIDATOR_CONTRACT_MISSING")
    try:
        result = subprocess.run(
            [sys.executable, str(root / SMOKE_VALIDATOR)],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        _fail("SMOKE_VALIDATOR_UNAVAILABLE")
    if result.returncode != 0 or result.stdout.strip() != "BOX4_DOCUMENT_REVIEW_SMOKE_OK=1":
        _fail("SMOKE_VALIDATOR_FAILED")


def _is_box4_runtime_dependency_file(changed: str) -> bool:
    return changed.replace("\\", "/") in BOX4_RUNTIME_DEPENDENCY_FILES


def _check_dependency_files_unchanged(root: Path) -> None:
    if any(_is_box4_runtime_dependency_file(changed) for changed in _changed_files(root)):
        _fail("DEPENDENCY_FILE_CHANGED")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    _check_review_service(root)
    _check_prompt(root)
    _check_wiring(root)
    _check_card_grid(root)
    _check_renderer(root)
    _check_tests(root)
    _check_smoke_validator(root)
    _check_dependency_files_unchanged(root)
    print("BOX4_DOCUMENT_REVIEW_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
