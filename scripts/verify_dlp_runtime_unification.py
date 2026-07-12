#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path


CARD_FILES = (
    "butler_pc_core/cards/box3/security.py",
    "butler_pc_core/cards/box4/review_service.py",
    "butler_pc_core/cards/box6/form_fill_service.py",
)
FORBIDDEN_CARD_NAMES = {
    "_SECRET_VALUE_RE",
    "_EMAIL_RE",
    "_PHONE_RE",
    "_KOREAN_RRN_RE",
    "_CARD_OR_ACCOUNT_RE",
    "_ZERO_WIDTH_CHARS",
    "_KOREAN_DIGIT_CHARS",
}
FORBIDDEN_RAW_SINK_NAMES = {"match.group", "matched_text", "snippet", "file_path"}


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _run_dynamic_probes(root: Path) -> dict[str, bool]:
    sys.path.insert(0, str(root))
    try:
        from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
        from butler_pc_core.connect_loop.scan_normalization import (
            _parse_observed_confusable_asset,
            load_observed_confusable_mappings,
        )
        from butler_pc_core.dlp.runtime import (
            SAFE_SECRET_REPLACEMENT,
            redact_fail_closed,
            scan_reason_codes,
            scan_runtime,
        )

        too_long = "x" * 200_001
        digest_rich = (("sha256:" + "a" * 64 + " ") * 4_000).strip()
        unsafe_replacement = "token: abcdefghijklmno1"
        asset = root / "butler_pc_core/connect_loop/observed_confusable_codepoints.v1.json"
        asset_data = json.loads(asset.read_text(encoding="utf-8"))
        asset_parsed = _parse_observed_confusable_asset(asset_data)
        load_observed_confusable_mappings.cache_clear()

        redacted = redact_fail_closed("alice@example.com", replacement=unsafe_replacement)
        return {
            "DLP_TOO_LONG_BOX3_BLOCK": (
                scan_reason_codes(too_long) == ["SECRET"]
                and scan_runtime_text(too_long)["passed"] is False
            ),
            "DLP_RAW_LENGTH_LIMIT_ORDER_OK": (
                len(digest_rich) == 287_999 and scan_runtime(digest_rich).too_long is True
            ),
            "DLP_UNSAFE_REPLACEMENT_OUTPUT_ZERO": (
                redacted == SAFE_SECRET_REPLACEMENT
                and unsafe_replacement not in redacted
                and not scan_runtime(redacted).any_detected
            ),
            "DLP_OBSERVED_CONFUSABLE_ASSET_OK": (
                asset_parsed == () and load_observed_confusable_mappings() == ()
            ),
        }
    except Exception:
        return {
            "DLP_TOO_LONG_BOX3_BLOCK": False,
            "DLP_RAW_LENGTH_LIMIT_ORDER_OK": False,
            "DLP_UNSAFE_REPLACEMENT_OUTPUT_ZERO": False,
            "DLP_OBSERVED_CONFUSABLE_ASSET_OK": False,
        }
    finally:
        if sys.path and sys.path[0] == str(root):
            sys.path.pop(0)


def _run_full_suite_without_deselect(root: Path) -> bool:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/dlp",
        "tests/connect_loop",
        "tests/cards/box3",
        "tests/cards/box4/test_review_service.py",
        "tests/cards/box6/test_form_fill_service.py",
        "-q",
    ]
    result = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True)
    return result.returncode == 0 and "deselect" not in result.stdout.casefold()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-suite", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    errors: list[str] = []
    redactor_defs: list[str] = []

    for relative in CARD_FILES:
        path = root / relative
        source = path.read_text(encoding="utf-8")
        tree = _parse(path)
        if "unicodedata.normalize" in source or "_ZERO_WIDTH_CHARS" in source or "_KOREAN_DIGIT" in source:
            errors.append(f"LOCAL_NORMALIZATION_COPY:{relative}")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_redact_secret_value":
                redactor_defs.append(relative)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in FORBIDDEN_CARD_NAMES:
                        errors.append(f"LOCAL_DLP_PATTERN:{relative}:{target.id}")
            if isinstance(node, ast.Raise) and node.exc is not None:
                rendered = ast.unparse(node.exc)
                if any(marker in rendered for marker in FORBIDDEN_RAW_SINK_NAMES):
                    errors.append(f"RAW_EXCEPTION_SURFACE:{relative}")
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if name.endswith((".debug", ".info", ".warning", ".error", ".exception")) or name == "print":
                    rendered = " ".join(ast.unparse(arg) for arg in node.args)
                    if any(marker in rendered for marker in FORBIDDEN_RAW_SINK_NAMES):
                        errors.append(f"RAW_LOG_SURFACE:{relative}")

    for path in (root / "butler_pc_core").rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative == "butler_pc_core/connect_loop/persisted_safety.py":
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module.endswith("persisted_safety") and any(alias.name == "_dlp_scan_all" for alias in node.names):
                errors.append(f"PRIVATE_DLP_IMPORT:{relative}")

    if redactor_defs:
        errors.append("LOCAL_REDACTOR_DEFS:" + ",".join(redactor_defs))

    runtime = root / "butler_pc_core/dlp/runtime.py"
    if not runtime.is_file():
        errors.append("RUNTIME_FACADE_MISSING")
    else:
        text = runtime.read_text(encoding="utf-8")
        for marker in ("def scan_runtime", "def scan_reason_codes", "def redact_fail_closed"):
            if marker not in text:
                errors.append("RUNTIME_API_MISSING:" + marker)
        if "scan_runtime(candidate)" not in text:
            errors.append("POST_REDACTION_RESCAN_MISSING")
        if text.count("def redact_fail_closed") != 1 or "_must_full_scalar_redact" not in text:
            errors.append("SHARED_FAIL_CLOSED_REDACTOR_INVALID")
        if "logging" in text or "print(" in text:
            errors.append("RUNTIME_RAW_LOG_SURFACE_PRESENT")

    dynamic = _run_dynamic_probes(root)
    errors.extend(name for name, passed in dynamic.items() if not passed)
    full_suite_passed = _run_full_suite_without_deselect(root) if args.run_suite else None
    if full_suite_passed is False:
        errors.append("DLP_FULL_SUITE_NO_DESELECT")

    print(f"DLP_RUNTIME_UNIFICATION_VERIFY={0 if errors else 1}")
    for name, passed in dynamic.items():
        print(f"{name}={1 if passed else 0}")
    if full_suite_passed is not None:
        print(f"DLP_FULL_SUITE_NO_DESELECT={1 if full_suite_passed else 0}")
    for error in errors:
        print(f"ERROR_CODE={error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
