from __future__ import annotations

import json
from pathlib import Path

from scripts.convert.convert_verify_v2 import verify


def test_verify_passes_from_bundle_root(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root)
    result = verify()
    assert result["all_pass"] is True
    payload = json.loads((root / "tmp" / "convert_verify_result.json").read_text(encoding="utf-8"))
    assert payload["all_pass"] is True
