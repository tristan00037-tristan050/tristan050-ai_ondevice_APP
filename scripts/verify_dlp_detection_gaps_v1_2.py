#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


TARGET = Path("butler_pc_core/connect_loop/persisted_safety.py")
TEST_TARGET = Path("tests/connect_loop/test_dlp_detection_gaps_v1_2.py")

REQUIRED_SOURCE_TOKENS = (
    "import unicodedata",
    "_HYPHEN_CHARS",
    "_ACCOUNT_HYPHEN_RE",
    "_has_hyphenated_account",
    "_KO_SECRET_RE",
    "_KO_SECRET_SAFE_START",
    "_has_ko_secret",
    'unicodedata.normalize("NFKC", value)',
    "_CARD_OR_ACCOUNT_RE.search(scan_value)",
    "_has_hyphenated_account(scan_value)",
    "_SECRET_RE.search(scan_value) or _has_ko_secret(scan_value)",
)
REQUIRED_TEST_TOKENS = (
    "110-234-567890",
    "110‐234‐567890",
    "2026-07-04",
    "비밀번호는 1234야",
    "비밀번호 정책을 변경합니다",
    "test_existing_dlp_patterns_keep_detecting",
    "test_dlp_hyphen_helper_linear_time",
    "RAW_OR_SECRET_VALUE_FORBIDDEN",
)
LEGACY_PATTERN_SNIPPETS = (
    r'_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")',
    r'_SECRET_RE = re.compile(',
    r'r"sk-[a-z0-9][a-z0-9._-]{10,})"',
)


def _fail(code: str) -> None:
    print("DLP_GAP_PATCH_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _read(root: Path, rel: Path) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError:
        _fail("FILE_MISSING")


def _function_segment(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    _fail("FUNCTION_MISSING")


def _check_required_tokens(source: str, test_source: str) -> None:
    for token in REQUIRED_SOURCE_TOKENS:
        if token not in source:
            _fail("SOURCE_TOKEN_MISSING")
    for token in REQUIRED_TEST_TOKENS:
        if token not in test_source:
            _fail("TEST_TOKEN_MISSING")


def _check_legacy_patterns_preserved(source: str) -> None:
    for snippet in LEGACY_PATTERN_SNIPPETS:
        if snippet not in source:
            _fail("LEGACY_PATTERN_DRIFT")


def _check_digit_count_helper(source: str) -> None:
    helper = _function_segment(source, "_has_hyphenated_account")
    if "10 <= digit_count <= 20" not in helper:
        _fail("DIGIT_COUNT_GUARD_MISSING")
    if "findall(" in helper or "match.group(0)" in helper:
        _fail("ACCOUNT_HELPER_RAW_ECHO_RISK")


def _check_secret_safe_word_helper(source: str) -> None:
    helper = _function_segment(source, "_has_ko_secret")
    if "token.startswith(_KO_SECRET_SAFE_START)" not in helper:
        _fail("KO_SECRET_SAFE_WORD_GUARD_MISSING")
    if not re.search(r"char\.isdigit\(\).*char\.isascii\(\).*isalnum", helper, flags=re.S):
        _fail("KO_SECRET_SIGNAL_GUARD_MISSING")


def _check_scan_result_shape(source: str) -> None:
    segment = _function_segment(source, "_dlp_scan_all")
    forbidden = ("match.group", "findall(", "snippet", "value[:", "return scan_value", "print(")
    if any(token in segment for token in forbidden):
        _fail("DLP_SCAN_RAW_ECHO_RISK")
    if "DlpScanResult(" not in segment:
        _fail("DLP_SCAN_RESULT_NOT_BOOLEAN_STRUCT")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    source = _read(root, TARGET)
    test_source = _read(root, TEST_TARGET)
    _check_required_tokens(source, test_source)
    _check_legacy_patterns_preserved(source)
    _check_digit_count_helper(source)
    _check_secret_safe_word_helper(source)
    _check_scan_result_shape(source)
    print("DLP_GAP_PATCH_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
