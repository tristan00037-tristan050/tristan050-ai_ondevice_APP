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
    "_require_evidence_digest",
}
FORBIDDEN_RAW_GREP_PATTERNS = (
    "evidence_digest or",
    "or context_digest",
    "or payload_digest",
    "DEFAULT_EVIDENCE_DIGEST",
    "data.get('verified",
    'data.get("verified',
    "data.get('evidence_digest'",
    'data.get("evidence_digest"',
    "ArtifactQueue",
    "print(",
    "repr(",
    "prompt",
    "response",
    "user_name",
    "messenger",
)
FALLBACK_NAME_RE = re.compile(r"(?:context_digest|payload_digest|DEFAULT_EVIDENCE_DIGEST)")


class StaticVerifier(ast.NodeVisitor):
    def __init__(self) -> None:
        self.failures: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        target_names = {self._name(target) for target in node.targets}
        if "evidence_digest" in target_names:
            self._check_no_fallback(node.value, "evidence_digest assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._name(node.target) == "evidence_digest" and node.value is not None:
            self._check_no_fallback(node.value, "evidence_digest annotated assignment")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_get_call(node) and len(node.args) >= 2:
            key = self._literal_string(node.args[0])
            if key in {"verified_by", "verified_at", "evidence_ref", "evidence_digest"}:
                self.failures.append(f"default injection via .get for {key}")
        self.generic_visit(node)

    def _check_no_fallback(self, node: ast.AST, where: str) -> None:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            rendered = ast.unparse(node) if hasattr(ast, "unparse") else "<boolop>"
            if FALLBACK_NAME_RE.search(rendered):
                self.failures.append(f"BoolOp fallback in {where}: {rendered}")
        if isinstance(node, ast.Name) and node.id in {"context_digest", "payload_digest", "DEFAULT_EVIDENCE_DIGEST"}:
            self.failures.append(f"direct fallback source in {where}: {node.id}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == "DEFAULT_EVIDENCE_DIGEST":
            self.failures.append(f"default evidence digest literal in {where}")

    @staticmethod
    def _name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _is_get_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Attribute) and node.func.attr == "get"

    @staticmethod
    def _literal_string(node: ast.AST) -> str | None:
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _load_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function_calls(tree: ast.Module, function_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return _calls_inside(node)
    return set()


def _class_method_calls(tree: ast.Module, class_name: str, method_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return _calls_inside(child)
    return set()


def _calls_inside(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
    return calls


def _raw_grep_failures(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    failures = []
    for pattern in FORBIDDEN_RAW_GREP_PATTERNS:
        if pattern in text:
            failures.append(f"forbidden raw grep pattern in {path.name}: {pattern}")
    return failures


def verify(repo_root: Path) -> list[str]:
    chat_path = repo_root / "butler_pc_core" / "learning_adapters" / "chat_context.py"
    contract_path = repo_root / "butler_pc_core" / "learning_core" / "contracts.py"

    failures: list[str] = []
    if not chat_path.exists():
        return [f"missing file: {chat_path}"]
    if not contract_path.exists():
        return [f"missing file: {contract_path}"]

    for path in (chat_path, contract_path):
        if path == chat_path:
            failures.extend(_raw_grep_failures(path))
        tree = _load_tree(path)
        visitor = StaticVerifier()
        visitor.visit(tree)
        failures.extend(f"{path.name}: {failure}" for failure in visitor.failures)

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

    contract_functions = {node.name for node in contract_tree.body if isinstance(node, ast.FunctionDef)}
    for required_function in REQUIRED_CHAT_CALLS | {"validate_digest_or_drop", "canonical_digest"}:
        if required_function not in contract_functions and required_function != "validate_evidence_ref":
            failures.append(f"contracts.py missing {required_function}")

    required_literals = (
        "integrated_learning_verifier",
        "privacy_officer",
        "security_reviewer",
        "DENY_EVIDENCE_REF_RE",
        "EVIDENCE_REF_RE",
        "butler/evidence/",
        "(?:vault|keyring)",
        "{16,128}",
    )
    contract_text = contract_path.read_text(encoding="utf-8")
    for literal in required_literals:
        if literal not in contract_text:
            failures.append(f"contracts.py missing literal: {literal}")

    return failures


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    failures = verify(repo_root)
    if failures:
        print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0")
        print("CONTRACT_STATIC_VERIFIER_FAIL=1")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("CHAT_CONTEXT_PRODUCER_CONTRACT_OK=1")
    print("CONTRACT_STATIC_VERIFIER_FAIL=0")
    print("provenance_validators=validate_verified_by,validate_verified_at,validate_evidence_ref,_require_evidence_digest")
    print("evidence_digest_fallback_patterns=absent")
    print("evidence_ref_token_min_length=16")
    print("artifact_queue_direct_append=absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
