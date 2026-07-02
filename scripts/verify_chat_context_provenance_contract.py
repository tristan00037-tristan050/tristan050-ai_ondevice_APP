#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


REQUIRED_CHAT_CALLS = {
    "validate_verified_by",
    "validate_verified_at",
    "validate_evidence_ref",
}
FORBIDDEN_DEFAULT_INJECTION_RE = re.compile(
    r"\.get\s*\(\s*['\"](?:verified_by|verified_at|evidence_ref|evidence_digest)['\"]\s*,"
)
FORBIDDEN_RUNTIME_PATTERNS = (
    "ArtifactQueue",
    "print(",
    "repr(",
)


def _load_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_calls(tree: ast.Module, function_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            calls: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name):
                        calls.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        calls.add(func.attr)
            return calls
    return set()


def _class_method_calls(tree: ast.Module, class_name: str, method_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    calls: set[str] = set()
                    for sub in ast.walk(child):
                        if isinstance(sub, ast.Call):
                            func = sub.func
                            if isinstance(func, ast.Name):
                                calls.add(func.id)
                            elif isinstance(func, ast.Attribute):
                                calls.add(func.attr)
                    return calls
    return set()


def verify(repo_root: Path) -> list[str]:
    chat_path = repo_root / "butler_pc_core" / "learning_adapters" / "chat_context.py"
    contract_path = repo_root / "butler_pc_core" / "learning_core" / "contracts.py"

    failures: list[str] = []
    if not chat_path.exists():
        return [f"missing file: {chat_path}"]
    if not contract_path.exists():
        return [f"missing file: {contract_path}"]

    chat_text = chat_path.read_text(encoding="utf-8")
    contract_text = contract_path.read_text(encoding="utf-8")

    for pattern in FORBIDDEN_RUNTIME_PATTERNS:
        if pattern in chat_text:
            failures.append(f"forbidden runtime pattern in chat_context.py: {pattern}")

    if FORBIDDEN_DEFAULT_INJECTION_RE.search(chat_text) or FORBIDDEN_DEFAULT_INJECTION_RE.search(contract_text):
        failures.append("default provenance injection pattern detected")

    chat_tree = _load_tree(chat_path)
    contract_tree = _load_tree(contract_path)

    provenance_calls = _function_calls(chat_tree, "validate_chat_context_provenance")
    missing_calls = sorted(REQUIRED_CHAT_CALLS - provenance_calls)
    if missing_calls:
        failures.append("validate_chat_context_provenance missing calls: " + ",".join(missing_calls))

    adapter_calls = _class_method_calls(chat_tree, "ChatContextAdapter", "verify")
    if "validate_chat_context_provenance" not in adapter_calls:
        failures.append("ChatContextAdapter.verify does not call validate_chat_context_provenance")
    if "validate_chat_context_source_refs" not in adapter_calls:
        failures.append("ChatContextAdapter.verify does not call validate_chat_context_source_refs")

    for required_function in REQUIRED_CHAT_CALLS:
        if required_function not in {node.name for node in contract_tree.body if isinstance(node, ast.FunctionDef)}:
            failures.append(f"contracts.py missing {required_function}")

    required_literals = (
        "integrated_learning_verifier",
        "privacy_officer",
        "security_reviewer",
        "EVIDENCE_REF_DENY_RE",
        "vault://butler/evidence/",
        "keyring://butler/evidence/",
    )
    for literal in required_literals:
        if literal not in contract_text:
            failures.append(f"contracts.py missing literal: {literal}")

    return failures


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    failures = verify(repo_root)
    if failures:
        print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=1")
    print("provenance_validators=validate_verified_by,validate_verified_at,validate_evidence_ref")
    print("default_injection_patterns=absent")
    print("artifact_queue_direct_append=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
