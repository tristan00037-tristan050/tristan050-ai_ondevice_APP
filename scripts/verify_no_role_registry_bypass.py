#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / "butler_pc_core", ROOT / "tests"]
BASE_CALL_ALLOWLIST = {
    "butler_pc_core/company_policy/admin_auth.py",
    "butler_pc_core/sidecar/routes/admin_role_registry.py",
    "tests/company_policy/test_admin_gate_hardening.py",
    "tests/company_policy/test_role_registry_admin_auth_integration.py",
    "tests/company_policy/test_role_registry_routes.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def main() -> int:
    for path in _iter_python_files():
        rel = _rel(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            print("ROLE_REGISTRY_BYPASS_SCAN_SYNTAX_ERROR=1")
            return 1
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "enforce_role_registry" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                    print("ROLE_REGISTRY_BYPASS_KEYWORD_FOUND=1")
                    return 1
            if _call_name(node.func) == "_verify_admin_context_base" and rel not in BASE_CALL_ALLOWLIST:
                print("ROLE_REGISTRY_BASE_CALL_OUTSIDE_ALLOWLIST=1")
                return 1
    print("ROLE_REGISTRY_BYPASS_ZERO=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
