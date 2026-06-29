#!/usr/bin/env python3
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
MATCHER = ROOT / "butler_pc_core/company_profile/matcher.py"
CLASSIFIER = ROOT / "butler_pc_core/accounting/classifier.py"
TEST = ROOT / "tests/accounting/test_self_transfer_guard.py"


def require(cond: bool, code: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL:{code}")


def read(path: Path) -> str:
    require(path.exists(), f"MISSING:{path}")
    return path.read_text(encoding="utf-8")


def func_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def regex_pattern(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        if not value.args or not isinstance(value.args[0], ast.Constant):
            continue
        pattern = value.args[0].value
        if isinstance(pattern, str):
            return pattern
    return ""


def split_regex_alternatives(pattern: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    escaped = False
    char_class_depth = 0
    for ch in pattern:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            continue
        if ch == "[":
            char_class_depth += 1
        elif ch == "]" and char_class_depth:
            char_class_depth -= 1
        if ch == "|" and char_class_depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def is_bare_replacement_alternative(part: str) -> bool:
    token = part.strip()
    token = re.sub(r"\\s[*+?]|\s+", "", token)
    token = re.sub(r"^\(\?:", "", token)
    while token.startswith("(") and token.endswith(")"):
        token = token[1:-1].strip()
    token = token.strip("^$")
    return token == "대체"


def has_bare_replacement_alternative(pattern: str) -> bool:
    return any(is_bare_replacement_alternative(part) for part in split_regex_alternatives(pattern))


def main() -> None:
    matcher = read(MATCHER)
    classifier = read(CLASSIFIER)
    tests = read(TEST)

    names = func_names(matcher)
    require("is_strong_internal_memo" in names, "STRONG_HELPER_MISSING")
    require("is_weak_transfer_memo" in names, "WEAK_HELPER_MISSING")
    strong_pattern = regex_pattern(matcher, "_STRONG_INTERNAL_MEMO_RE")
    weak_pattern = regex_pattern(matcher, "_WEAK_TRANSFER_MEMO_RE")
    require(strong_pattern, "STRONG_REGEX_MISSING")
    require(weak_pattern, "WEAK_REGEX_MISSING")
    require("대체\\s*입금" in strong_pattern, "STRONG_REPLACEMENT_DEPOSIT_FULL_COMPOUND_MISSING")
    require("예금\\s*대체" in weak_pattern, "WEAK_DEPOSIT_REPLACEMENT_FULL_COMPOUND_MISSING")
    require(not has_bare_replacement_alternative(strong_pattern), "BARE_REPLACEMENT_PATTERN_FORBIDDEN")
    require(not has_bare_replacement_alternative(weak_pattern), "BARE_REPLACEMENT_PATTERN_FORBIDDEN")

    require("is_strong_internal_memo" in classifier, "CLASSIFIER_IMPORT_MISSING")
    order = re.findall(r'return "(ACCOUNT_VERIFICATION|SELF_HOLDER_MATCH|OWN_ACCOUNT_MATCH|STRONG_INTERNAL_MEMO)"', classifier)
    require(order[:4] == ["ACCOUNT_VERIFICATION", "SELF_HOLDER_MATCH", "OWN_ACCOUNT_MATCH", "STRONG_INTERNAL_MEMO"], f"PRIORITY_INVALID:{order[:4]}")

    require("사내식당" in tests and "사내복지비" in tests, "SANAE_FALSE_POSITIVE_TEST_MISSING")
    require(
        "test_strong_internal_memo_guarded_rows_do_not_call_ft_classify" in tests
        and 'monkeypatch.setattr(classifier, "ft_classify"' in tests
        and "STRONG_INTERNAL_MEMO" in tests,
        "FT_CLASSIFY_BYPASS_TEST_MISSING",
    )

    print("BOX5_GUARD_V2_CONTRACT_OK=1")


if __name__ == "__main__":
    main()
