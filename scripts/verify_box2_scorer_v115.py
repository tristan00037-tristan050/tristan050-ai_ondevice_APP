#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

EXPECTED = '1e0f2766be37586e16b3e63495dec7a8955d155b33c9a2ebd3f73243377b429d'


def calls_in_function(tree: ast.Module, name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            out: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    fn = child.func
                    if isinstance(fn, ast.Name):
                        out.add(fn.id)
                    elif isinstance(fn, ast.Attribute):
                        out.add(fn.attr)
            return out
    return set()


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    scorer = root / 'butler_pc_core/cards/box2/value_scorer_v115.py'
    if not scorer.exists():
        print('BOX2_SCORER_CONTRACT_OK=0')
        print('reason=SCORER_MODULE_MISSING')
        return 1
    text = scorer.read_text(encoding='utf-8')
    tree = ast.parse(text)
    failures: list[str] = []
    required = ['EXPECTED_EVAL_SHA256', 'CURRENCY_MAP', 'DATE_SLASH_RE', 'money_preserved', 'score_against_gold', 'summarize_scores']
    for item in required:
        if item not in text:
            failures.append('missing:' + item)
    if EXPECTED not in text:
        failures.append('full_sha_missing')
    if 'EXPECTED_EVAL_SHA256_PREFIX' in text or 'startswith(' in text:
        failures.append('prefix_sha_check_detected')
    if '0.85' in text or '+ 0.02' in text:
        failures.append('constant_scorer_detected')
    score_calls = calls_in_function(tree, 'score_against_gold')
    if 'money_preserved' not in score_calls or 'canonical_preserved' not in score_calls:
        failures.append('gold_score_not_using_currency_and_canonical')
    if failures:
        print('BOX2_SCORER_CONTRACT_OK=0')
        for failure in failures:
            print('FAIL=' + failure)
        return 1
    print('BOX2_SCORER_CONTRACT_OK=1')
    print('full_sha_binding=1')
    print('currency_over_credit_guard=1')
    print('slash_date_recall=1')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
