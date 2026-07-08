#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
SCAN_MODULE = Path("butler_pc_core/connect_loop/scan_normalization.py")
PERSISTED = Path("butler_pc_core/connect_loop/persisted_safety.py")
DLP_GUARD = Path("butler_pc_core/connect_loop/dlp_guard.py")
ATTACHMENT = Path("butler_pc_core/connect_loop/attachment_features.py")
LEARNING_GATE = Path("butler_pc_core/connect_loop/learning_candidate_gate.py")
ENTRYPOINTS = [PERSISTED, DLP_GUARD, ATTACHMENT, LEARNING_GATE]

BASE_REGEX_DIGESTS = {
    "_EMAIL_RE": "sha256:3d9d66f3eab57906312abeed64117d0100201ee255a90fd4909329846ea4e247",
    "_PHONE_RE": "sha256:fa1092d5c4ac6d4471c3363d57d226b20ec66d7a5f0c949fac8aa5498df6b184",
    "_KOREAN_RRN_RE": "sha256:228ed1970b2d2154cd84193ea24b299f8963d5825153f48ee766ca1599f1e216",
    "_CARD_OR_ACCOUNT_RE": "sha256:4f5bbf9e9840c365fbbcc28232c5d9965782ae2c629b21e7c1f1b724edce0d00",
}


def fail(code: str) -> None:
    print("DLP_SCAN_NORMALIZATION_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def read(rel: Path) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        fail("SOURCE_FILE_MISSING")


def assignment_digest(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    rendered = ast.get_source_segment(source, node) or ""
                    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    fail(f"REGEX_ASSIGNMENT_MISSING:{name}")


def imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def main() -> int:
    scan_source = read(SCAN_MODULE)
    persisted_source = read(PERSISTED)
    dlp_source = read(DLP_GUARD)
    attachment_source = read(ATTACHMENT)
    learning_source = read(LEARNING_GATE)

    for required in (
        "class ScanVariant",
        "class DlpScanResult",
        "def scan_variants",
        "def detect_any",
        "DLP_DETECTED_RAW",
        "DLP_DETECTED_NORMALIZED_VARIANT",
        "SCAN_INPUT_TOO_LONG",
        "unicodedata.normalize",
        "unicodedata.decimal",
        "Mn",
        "Me",
    ):
        if required not in scan_source:
            fail("SCAN_NORMALIZATION_API_MISSING")

    disallowed_imports = imported_modules(scan_source) - {"__future__", "re", "unicodedata", "dataclasses", "typing", "collections"}
    if disallowed_imports:
        fail("SCAN_NORMALIZATION_THIRD_PARTY_IMPORT")

    for name, expected in BASE_REGEX_DIGESTS.items():
        if assignment_digest(persisted_source, name) != expected:
            fail(f"BASE_REGEX_DIGEST_DRIFT:{name}")

    if "unicodedata.normalize" in persisted_source:
        fail("PERSISTED_DIRECT_NORMALIZE_REMAINS")
    if "detect_any(_PII_PATTERNS" not in persisted_source:
        fail("PERSISTED_DETECT_ANY_MISSING")
    if "scan_runtime_text" not in dlp_source or "_dlp_scan_all" not in dlp_source:
        fail("DLP_GUARD_COMMON_WRAPPER_MISSING")
    if "scan_runtime_text" not in learning_source:
        fail("LEARNING_GATE_DLP_WRAPPER_MISSING")

    if any(token in scan_source for token in ("print(", "logging.", "variant.text", "match.group(0)", "matched_text")):
        fail("RAW_OR_NORMALIZED_VALUE_LOGGING_RISK")
    if any(token in persisted_source for token in ("variant.text", "match.group(0)", "normalized_value")):
        fail("PERSISTED_RAW_ECHO_RISK")

    # Strict mode: this should move to scan_runtime_text/detect_any in the final PR.
    if "_EMAIL_RE.search(text)" in attachment_source or "_SECRET_RE.search(text)" in attachment_source or "_PATH_RE.search(text)" in attachment_source:
        fail("ATTACHMENT_FEATURES_DIRECT_REGEX_REMAINS")

    print("DLP_SCAN_NORMALIZATION_OK=1")
    print("SCAN_VARIANTS_API=1")
    print("ENTRYPOINT_PERSISTED_COMMON=1")
    print("ENTRYPOINT_DLP_GUARD_COMMON=1")
    print("ENTRYPOINT_LEARNING_GATE_COMMON=1")
    print("ENTRYPOINT_ATTACHMENT_FEATURES_COMMON=1")
    print("RAW_NORMALIZED_ECHO=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
