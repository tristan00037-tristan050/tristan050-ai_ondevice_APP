"""test_derived_artifact_raw_text_retention_zero.py — raw text 보존 0 (M-54/M-60)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVAL_SET = ROOT / "evaluation/card2/eval_set_v1.jsonl"

FORBIDDEN_DATA_FIELDS = {"raw_text", "source_text", "original_text",
                         "raw_paragraph", "original_paragraph"}


def test_eval_set_exists():
    assert EVAL_SET.exists(), "eval_set_v1.jsonl 부재"


def test_eval_items_have_no_raw_text_fields():
    for line in EVAL_SET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        leaked = FORBIDDEN_DATA_FIELDS & set(item.keys())
        assert not leaked, f"{item.get('case_id')} raw 필드 누출: {leaked}"
        assert item.get("raw_text_retained") is False


def test_eval_items_are_redacted():
    for line in EVAL_SET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        assert "[REDACTED" in item["text_redacted"]
