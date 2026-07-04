#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


REWRITE_PATH = Path("butler_pc_core/cards/box2/rewrite_service.py")
BASELINE_HEAD = "128c3d35ef6abbd13a90af2fe5a8854518a0fc1e"
EXTRACTION_FUNCTIONS = (
    "_iter_labeled_spans",
    "_extract_unit_price_value",
    "_money_has_amount_context",
    "_extract_amount",
)
FORBIDDEN_REPORT_KEYS = {
    "foreign",
    "foreign_doc",
    "our_format",
    "input_1",
    "input_2",
    "must_keep",
    "fields",
    "rewritten_doc",
    "raw",
    "raw_text",
}


def _fail(code: str) -> None:
    print("BOX2_SCORER_CONTRACT_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def _load_source(root: Path) -> str:
    try:
        return (root / REWRITE_PATH).read_text(encoding="utf-8")
    except OSError:
        _fail("REWRITE_SERVICE_MISSING")


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError:
        _fail("REWRITE_SERVICE_SYNTAX_INVALID")


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    _fail(f"FUNCTION_MISSING_{name}")


def _function_source(source: str, name: str) -> str:
    tree = _parse(source)
    node = _function_node(tree, name)
    segment = ast.get_source_segment(source, node)
    if not segment:
        _fail(f"FUNCTION_SOURCE_MISSING_{name}")
    return segment


def _baseline_source(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "show", f"{BASELINE_HEAD}:{REWRITE_PATH.as_posix()}"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        _fail("BASELINE_SOURCE_UNAVAILABLE")


def _check_extraction_functions_unchanged(root: Path, source: str) -> None:
    baseline = _baseline_source(root)
    for name in EXTRACTION_FUNCTIONS:
        if _function_source(source, name) != _function_source(baseline, name):
            _fail(f"EXTRACTION_FUNCTION_CHANGED_{name}")


def _check_no_constant_scorer(source: str) -> None:
    forbidden_patterns = (
        r"semantic_preservation_score[\"']?\s*:\s*0\.85\b",
        r"\breturn\s+0\.85\b",
        r"\+\s*0\.02\b",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, source):
            _fail("CONSTANT_SCORER_FORBIDDEN")


def _check_eval_path_and_sha_binding(source: str) -> None:
    if 'butler-ct-shared/code_archive/box2_eval' not in source:
        _fail("BOX2_EVALSET_PATH_NOT_REGISTERED")
    if 'EXPECTED_EVAL_SHA256 = "1e0f2766be37586e16b3e63495dec7a8955d155b33c9a2ebd3f73243377b429d"' not in source:
        _fail("BOX2_EVALSET_FULL_SHA_MISSING")
    if "EXPECTED_EVAL_SHA256_PREFIX" in source or ".startswith(EXPECTED_EVAL_SHA256" in source:
        _fail("BOX2_EVALSET_PREFIX_SHA_FORBIDDEN")
    if "BOX2_EVALSET_SHA_DRIFT" not in source:
        _fail("BOX2_EVALSET_SHA_DRIFT_CODE_MISSING")


def _check_money_and_date_guards(source: str, tree: ast.Module) -> None:
    if "CURRENCY_MAP" not in source or "_money_preserved" not in source:
        _fail("MONEY_PRESERVATION_GUARD_MISSING")
    money_node = _function_node(tree, "_money_preserved")
    money_source = ast.get_source_segment(source, money_node) or ""
    if "gold_currency != observed_currency" not in money_source:
        _fail("MONEY_CURRENCY_MISMATCH_NOT_BLOCKED")
    if "_find_gold_value_stop" not in source or "_is_slash_date_context" not in source:
        _fail("SLASH_DATE_RECALL_GUARD_MISSING")


def _check_recursive_digest_safe(source: str, tree: ast.Module) -> None:
    node = _function_node(tree, "_assert_digest_safe_report")
    guard_source = ast.get_source_segment(source, node) or ""
    if "Mapping" not in guard_source or "list" not in guard_source or "check(child)" not in guard_source:
        _fail("RECURSIVE_DIGEST_SAFE_GUARD_MISSING")


def _check_gold_references(tree: ast.Module) -> None:
    node = _function_node(tree, "score_rewrite_against_gold")
    names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
    if not {"must_keep", "fields"}.issubset(names):
        _fail("GOLD_LABELS_NOT_USED")

    eval_node = _function_node(tree, "evaluate_eval_set")
    eval_source_names = {
        child.value
        for child in ast.walk(eval_node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }
    if {"foreign_doc", "our_format", "input_1", "input_2"}.intersection(eval_source_names):
        _fail("LEGACY_EVAL_KEYS_USED")


def _check_report_keys(tree: ast.Module) -> None:
    report_functions = {"_empty_eval", "_aggregate_scores"}
    for function_name in report_functions:
        node = _function_node(tree, function_name)
        for child in ast.walk(node):
            if not isinstance(child, ast.Dict):
                continue
            keys = {
                key.value
                for key in child.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if FORBIDDEN_REPORT_KEYS.intersection(keys):
                _fail("REPORT_FORBIDDEN_KEY")


def _check_version(source: str) -> None:
    if 'SCORER_VERSION = "box2.eval.v3_gold"' not in source:
        _fail("SCORER_VERSION_MISSING")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    source = _load_source(root)
    tree = _parse(source)
    _check_version(source)
    _check_no_constant_scorer(source)
    _check_eval_path_and_sha_binding(source)
    _check_money_and_date_guards(source, tree)
    _check_recursive_digest_safe(source, tree)
    _check_gold_references(tree)
    _check_report_keys(tree)
    _check_extraction_functions_unchanged(root, source)
    print("BOX2_SCORER_CONTRACT_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
