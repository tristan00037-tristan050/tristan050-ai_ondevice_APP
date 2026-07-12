from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cards_use_public_facade_and_no_local_redactor_defs():
    paths = [
        ROOT / "butler_pc_core/cards/box3/security.py",
        ROOT / "butler_pc_core/cards/box4/review_service.py",
        ROOT / "butler_pc_core/cards/box6/form_fill_service.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "butler_pc_core.dlp.runtime" in source
        assert "_dlp_scan_all" not in source
        for node in ast.walk(tree):
            assert not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_redact_secret_value")
