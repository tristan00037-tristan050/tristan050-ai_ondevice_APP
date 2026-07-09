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
TESTS = (
    "tests/connect_loop/test_dlp_scan_normalization.py",
    "tests/connect_loop/test_dlp_detection_gaps_v1_2.py",
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
STANDARD_LIBRARY_IMPORTS = {"__future__", "dataclasses", "re", "typing", "unicodedata"}


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
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        segment = ast.get_source_segment(source, node) or ""
        return hashlib.sha256(segment.encode("utf-8")).hexdigest()
    _fail("REGEX_ASSIGNMENT_MISSING")
    raise AssertionError("unreachable")


def _check_entrypoint_integration(root: Path) -> None:
    sources = {name: _read(root, rel) for name, rel in ENTRYPOINTS.items()}
    for source in sources.values():
        _parse(source)
    if "detect_any(" not in sources["persisted_safety"]:
        _fail("PERSISTED_SAFETY_NOT_USING_DETECT_ANY")
    if "_dlp_scan_all(" not in sources["dlp_guard"]:
        _fail("DLP_GUARD_NOT_USING_COMMON_SCAN")
    if "_dlp_scan_all(" not in sources["attachment_features"]:
        _fail("ATTACHMENT_FEATURES_NOT_USING_COMMON_SCAN")
    if "scan_runtime_text(" not in sources["learning_candidate_gate"]:
        _fail("LEARNING_GATE_NOT_USING_COMMON_DLP")
    for name, source in sources.items():
        if name != "persisted_safety" and "unicodedata.normalize" in source:
            _fail("ENTRYPOINT_DIRECT_NFKC_REMAINING")
    if "unicodedata.normalize" in sources["persisted_safety"]:
        _fail("ENTRYPOINT_DIRECT_NFKC_REMAINING")


def _check_attachment_features_has_no_direct_regex_scan(root: Path) -> None:
    source = _read(root, ENTRYPOINTS["attachment_features"])
    tree = _parse(source)
    removed_symbols = {"_EMAIL_RE", "_SECRET_RE", "_PATH_RE"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in removed_symbols:
            _fail("ATTACHMENT_UNUSED_REGEX_REMAINS")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "re":
                    _fail("ATTACHMENT_DIRECT_REGEX_SCAN_REMAINS")
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "re" and func.attr in {"compile", "search", "match", "fullmatch", "findall", "finditer"}:
                _fail("ATTACHMENT_DIRECT_REGEX_SCAN_REMAINS")


def _check_regex_digests(root: Path) -> None:
    source = _read(root, ENTRYPOINTS["persisted_safety"])
    tree = _parse(source)
    for name, expected in EXPECTED_REGEX_DIGESTS.items():
        if _assignment_digest(source, tree, name) != expected:
            _fail("REGEX_DIGEST_DRIFT")


def _check_raw_zero_source(root: Path) -> None:
    forbidden = (
        "normalized_text",
        "match.group(0)",
        "match.groups(",
        "findall(",
        "matched_text",
        "substring",
        "print(",
    )
    for rel in (*ENTRYPOINTS.values(), SCAN_MODULE):
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
    required_api = {"ScanVariant", "DlpScanResult", "scan_variants", "detect_any"}
    exported = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    if not required_api <= exported:
        _fail("SCAN_MODULE_PUBLIC_API_MISSING")


def _run_tests(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(result.stdout, end="")
        _fail("DLP_SCAN_NORMALIZATION_TESTS_FAILED")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    _check_entrypoint_integration(root)
    _check_attachment_features_has_no_direct_regex_scan(root)
    _check_regex_digests(root)
    _check_raw_zero_source(root)
    _check_scan_module_stdlib_only(root)
    _run_tests(root)
    print("DLP_SCAN_NORMALIZATION_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
