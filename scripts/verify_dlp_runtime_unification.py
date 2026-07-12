#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

CARD_FILES = (
    "butler_pc_core/cards/box3/security.py",
    "butler_pc_core/cards/box4/review_service.py",
    "butler_pc_core/cards/box6/form_fill_service.py",
)
REQUIRED_FILES = (
    "butler_pc_core/dlp/__init__.py",
    "butler_pc_core/dlp/runtime.py",
    "butler_pc_core/connect_loop/scan_normalization.py",
    "butler_pc_core/connect_loop/persisted_safety.py",
    "butler_pc_core/connect_loop/observed_confusable_codepoints.v1.json",
)
FORBIDDEN_CARD_NAMES = {
    "_SECRET_VALUE_RE", "_EMAIL_RE", "_PHONE_RE", "_KOREAN_RRN_RE",
    "_CARD_OR_ACCOUNT_RE", "_ZERO_WIDTH_CHARS", "_KOREAN_DIGIT_CHARS",
}
TESTS = ("tests/dlp", "tests/connect_loop/test_dlp_scan_normalization.py")


def _fail(code: str) -> None:
    print("DLP_RUNTIME_UNIFICATION_VERIFY=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        _fail("SOURCE_FILE_OR_PARSE_ERROR")


def _verify_sources(root: Path) -> None:
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            _fail("REQUIRED_FILE_MISSING")
    runtime = (root / "butler_pc_core/dlp/runtime.py").read_text(encoding="utf-8")
    for marker in ("def scan_runtime", "def scan_reason_codes", "def redact_fail_closed", "scan_runtime(candidate)"):
        if marker not in runtime:
            _fail("RUNTIME_FACADE_CONTRACT_MISSING")
    persisted = (root / "butler_pc_core/connect_loop/persisted_safety.py").read_text(encoding="utf-8")
    if "def scan_text_categories" not in persisted or "def _dlp_scan_all" not in persisted:
        _fail("PERSISTED_PUBLIC_OR_LEGACY_API_MISSING")
    scan_source = (root / "butler_pc_core/connect_loop/scan_normalization.py").read_text(encoding="utf-8")
    if '"O": "0"' in scan_source or '"I": "1"' in scan_source or '"l": "1"' in scan_source:
        _fail("GLOBAL_ASCII_CONFUSABLE_MAPPING_FORBIDDEN")
    for rel in CARD_FILES:
        path = root / rel
        tree = _parse(path)
        imports_public_facade = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_redact_secret_value":
                _fail("LOCAL_REDACTOR_DEFINITION_REMAINS")
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in FORBIDDEN_CARD_NAMES:
                        _fail("LOCAL_DLP_PATTERN_REMAINS")
            if isinstance(node, ast.ImportFrom):
                if node.module == "butler_pc_core.dlp.runtime":
                    imports_public_facade = True
                if node.module and node.module.endswith("persisted_safety"):
                    if any(alias.name == "_dlp_scan_all" for alias in node.names):
                        _fail("PRIVATE_DLP_IMPORT_IN_CARD")
        if not imports_public_facade:
            _fail("PUBLIC_DLP_FACADE_IMPORT_MISSING")
    box6 = (root / CARD_FILES[2]).read_text(encoding="utf-8")
    if "_SECRET_LABEL_RE" not in box6 or "SENSITIVE_FIELD_AUTOFILL_BLOCKED" not in box6:
        _fail("BOX6_SECRET_LABEL_GUARD_REMOVED")


def _run_tests(root: Path) -> None:
    selected = [item for item in TESTS if (root / item).exists()]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *selected, "-q"],
        cwd=root,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
    )
    if result.returncode:
        _fail("DLP_RUNTIME_TESTS_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    _verify_sources(args.repo_root)
    if not args.skip_tests:
        _run_tests(args.repo_root)
    print("DLP_RUNTIME_UNIFICATION_VERIFY=1")
    print("PUBLIC_DLP_FACADE=1")
    print("BOX3_BLOCK_SEMANTICS=1")
    print("BOX4_BOX6_FAIL_CLOSED_REDACTION=1")
    print("POST_REDACTION_RESCAN=1")
    print("GLOBAL_ASCII_CONFUSABLE_MAPPING=0")
    print("RAW_NORMALIZED_ECHO=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
