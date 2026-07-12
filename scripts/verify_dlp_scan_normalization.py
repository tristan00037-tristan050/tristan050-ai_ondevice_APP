#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

ENTRYPOINTS = {
    "persisted_safety": Path("butler_pc_core/connect_loop/persisted_safety.py"),
    "dlp_guard": Path("butler_pc_core/connect_loop/dlp_guard.py"),
    "attachment_features": Path("butler_pc_core/connect_loop/attachment_features.py"),
    "learning_candidate_gate": Path("butler_pc_core/connect_loop/learning_candidate_gate.py"),
}
SCAN_MODULE = Path("butler_pc_core/connect_loop/scan_normalization.py")
RUNTIME_FACADE = Path("butler_pc_core/dlp/runtime.py")
TESTS = (
    "tests/connect_loop/test_dlp_scan_normalization.py",
    "tests/connect_loop/test_dlp_detection_gaps_v1_2.py",
    "tests/dlp",
)
EXPECTED_REGEX_DIGESTS = {
    "_EMAIL_RE": "2f393e901451cb852312cc3fd1a9d5d6da30f02319e400cf9a243d0336f4c604",
    "_PHONE_RE": "78e41c34d55cd560229112a8ce769e08037882f2784056773e86e46744bffd35",
    "_KOREAN_RRN_RE": "ac04c77eec99d010c6768992eedca08722af0846e978982e8727958ebe704e11",
    "_CARD_OR_ACCOUNT_RE": "e04d253c2927e3a7fa0fe7d9d7214bf7fc2ab1826bef349e13243de726c24cfb",
    "_ACCOUNT_HYPHEN_RE": "28c93fcde632752f781fb1de8ad777aab5bdd5b0c66cc2a13658d078060b3461",
    "_SECRET_RE": "0d77f3171e2d5d228c27dd34dee2cd5024d790536c261f779dee4a88d991522e",
    "_KO_SECRET_RE": "8333b832fa08caf4c2dac15e157d26f05ec0a9bd9ca8d2d47847ace28864527c",
    "_LOCAL_PATH_RE": "1270a250890c83e00c094dc980143f313b508c85d5885bbc24fc734024ce2746",
}
STANDARD_LIBRARY_IMPORTS = {"__future__", "dataclasses", "json", "pathlib", "re", "typing", "unicodedata"}


def _fail(code: str) -> None:
    print("DLP_SCAN_NORMALIZATION_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _read(root: Path, rel: Path) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except OSError:
        _fail("FILE_MISSING")


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError:
        _fail("SOURCE_PARSE_ERROR")


def _assignment_digest(source: str, tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return hashlib.sha256((ast.get_source_segment(source, node) or "").encode("utf-8")).hexdigest()
    _fail("REGEX_ASSIGNMENT_MISSING")


def _check_entrypoint_integration(root: Path) -> None:
    sources = {name: _read(root, rel) for name, rel in ENTRYPOINTS.items()}
    for source in sources.values():
        _parse(source)
    if "scan_text_categories(" not in sources["persisted_safety"]:
        _fail("PERSISTED_PUBLIC_SCAN_MISSING")
    if "scan_runtime(" not in sources["dlp_guard"]:
        _fail("DLP_GUARD_NOT_USING_PUBLIC_FACADE")
    if "_dlp_scan_all(" not in sources["attachment_features"]:
        _fail("ATTACHMENT_FEATURES_COMMON_SCAN_MISSING")
    if "scan_runtime_text(" not in sources["learning_candidate_gate"]:
        _fail("LEARNING_GATE_NOT_USING_COMMON_DLP")
    if not (root / RUNTIME_FACADE).is_file():
        _fail("RUNTIME_FACADE_MISSING")
    for source in sources.values():
        if "unicodedata.normalize" in source:
            _fail("ENTRYPOINT_DIRECT_NFKC_REMAINING")


def _check_regex_digests(root: Path) -> None:
    source = _read(root, ENTRYPOINTS["persisted_safety"])
    tree = _parse(source)
    for name, expected in EXPECTED_REGEX_DIGESTS.items():
        if _assignment_digest(source, tree, name) != expected:
            _fail("REGEX_DIGEST_DRIFT")


def _check_raw_zero_source(root: Path) -> None:
    forbidden = ("match.group(0)", "match.groups(", "findall(", "matched_text", "print(")
    for rel in (*ENTRYPOINTS.values(), SCAN_MODULE, RUNTIME_FACADE):
        source = _read(root, rel)
        if any(token in source for token in forbidden):
            _fail("RAW_VALUE_LOGGING_RISK")


def _check_scan_module_stdlib_only(root: Path) -> None:
    source = _read(root, SCAN_MODULE)
    tree = _parse(source)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] not in STANDARD_LIBRARY_IMPORTS:
                    _fail("SCAN_MODULE_NON_STDLIB_IMPORT")
        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".", 1)[0]
            if module not in STANDARD_LIBRARY_IMPORTS:
                _fail("SCAN_MODULE_NON_STDLIB_IMPORT")
    required_api = {"ScanVariant", "DlpScanResult", "scan_variants", "detect_any", "detect_grouped"}
    exported = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    if not required_api <= exported:
        _fail("SCAN_MODULE_PUBLIC_API_MISSING")


def _run_tests(root: Path) -> None:
    tests = [test for test in TESTS if (root / test).exists()]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
    )
    if result.returncode:
        _fail("DLP_SCAN_NORMALIZATION_TESTS_FAILED")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    _check_entrypoint_integration(root)
    _check_regex_digests(root)
    _check_raw_zero_source(root)
    _check_scan_module_stdlib_only(root)
    _run_tests(root)
    print("DLP_SCAN_NORMALIZATION_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
