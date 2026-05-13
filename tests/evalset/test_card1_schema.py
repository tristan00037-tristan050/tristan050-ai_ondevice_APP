"""단계 6.5.5 Day 1 — Card1 EvalSet Schema 단위 테스트 (6건)."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "card1_eval_item.schema.json"

# jsonschema 미설치 시 전체 skip (CI 에선 설치 필요)
jsonschema = pytest.importorskip("jsonschema")
Draft202012Validator = jsonschema.Draft202012Validator


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def minimal_valid_item():
    return {
        "sample_id":              "card1_000001",
        "text_redacted":          "[DOCUMENT] 오늘 안에 요약해줘",
        "raw_digest16":           "sha256:0000000000000001",
        "source":                 "synthetic_gold",
        "intent_type":            "REQUEST",
        "deadline_type":          "SOFT",
        "deadline_is_actionable": False,
        "slice_tags":             ["document_task", "deadline_soft"],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "gold_reviewed",
    }


def test_schema_validates_minimal_valid_item(schema, minimal_valid_item):
    Draft202012Validator(schema).validate(minimal_valid_item)


def test_schema_rejects_missing_required_field(schema, minimal_valid_item):
    """sample_id 누락 → 위반."""
    bad = deepcopy(minimal_valid_item)
    del bad["sample_id"]
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert any("sample_id" in str(e.message) or "sample_id" in str(e.path) or
               "required" in str(e.message) for e in errs)


def test_schema_rejects_invalid_intent_type(schema, minimal_valid_item):
    bad = deepcopy(minimal_valid_item)
    bad["intent_type"] = "WHATEVER"
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0


def test_schema_rejects_invalid_deadline_type(schema, minimal_valid_item):
    bad = deepcopy(minimal_valid_item)
    bad["deadline_type"] = "DEADLINE"
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0


def test_schema_rejects_extra_property(schema, minimal_valid_item):
    """additionalProperties=false 검증."""
    bad = deepcopy(minimal_valid_item)
    bad["extra_unknown_field"] = "x"
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert any("additionalProperties" in e.message or "not allowed" in e.message
               for e in errs)


def test_schema_rejects_invalid_digest16_format(schema, minimal_valid_item):
    bad = deepcopy(minimal_valid_item)
    bad["raw_digest16"] = "md5:abcdef"   # wrong prefix
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0
