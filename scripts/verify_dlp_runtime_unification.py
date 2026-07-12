#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
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

    print(f"DLP_RUNTIME_UNIFICATION_VERIFY={0 if errors else 1}")
    for error in errors:
        print(f"ERROR_CODE={error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
