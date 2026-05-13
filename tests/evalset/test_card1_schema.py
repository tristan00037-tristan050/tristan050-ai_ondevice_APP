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
    """PR #703/#704 정정 후: synthetic_gold + text 필수 + reviewer 필수(gold_reviewed)."""
    return {
        "sample_id":              "card1_000001",
        "text":                   "[DOCUMENT] 오늘 안에 요약해줘",
        "text_redacted":          None,
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
        "reviewer":               {"id": "r1", "decision": "approved",
                                   "reviewed_at": "2026-05-13T09:00:00Z"},
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


# ── PR #703 P1 정정 회귀 (5건) ─────────────────────────────────────────

@pytest.fixture
def gold_item_with_text():
    return {
        "sample_id":              "card1_100001",
        "text":                   "회의록 정리해서 공유해 주세요",
        "text_redacted":          None,
        "raw_digest16":           "sha256:1111111111111111",
        "source":                 "synthetic_gold",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "gold_reviewed",
        "reviewer":               {"id": "r1", "decision": "approved",
                                   "reviewed_at": "2026-05-13T09:00:00Z"},
    }


@pytest.fixture
def userlog_item_with_redacted():
    return {
        "sample_id":              "card1_200001",
        "text":                   None,
        "text_redacted":          "[EMAIL]으로 보고서 보내주세요",
        "raw_digest16":           "sha256:2222222222222222",
        "source":                 "internal_log_redacted",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "draft",
    }


def test_schema_rejects_userlog_with_text_not_null(schema, userlog_item_with_redacted):
    """userlog_redacted 인데 text 가 string 이면 거부 (PII leak 경로 차단)."""
    bad = deepcopy(userlog_item_with_redacted)
    bad["text"] = "raw content here"
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0, "userlog_redacted 의 text 채워짐이 schema 위반 처리되어야 함"


def test_schema_rejects_synthetic_gold_without_text(schema, gold_item_with_text):
    """synthetic_gold 인데 text 가 null 이면 거부."""
    bad = deepcopy(gold_item_with_text)
    bad["text"] = None
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0


def test_schema_accepts_synthetic_gold_with_text(schema, gold_item_with_text):
    """synthetic_gold + text 채워짐 → PASS."""
    errs = list(Draft202012Validator(schema).iter_errors(gold_item_with_text))
    assert errs == [], f"unexpected errors: {[e.message for e in errs]}"


def test_schema_accepts_userlog_with_text_null(schema, userlog_item_with_redacted):
    """userlog_redacted + text=null + text_redacted 채워짐 → PASS."""
    errs = list(Draft202012Validator(schema).iter_errors(userlog_item_with_redacted))
    assert errs == [], f"unexpected errors: {[e.message for e in errs]}"


def test_schema_rejects_userlog_with_empty_text_redacted(schema, userlog_item_with_redacted):
    """text_redacted 가 빈 문자열이면 거부 (minLength 1)."""
    bad = deepcopy(userlog_item_with_redacted)
    bad["text_redacted"] = ""
    errs = list(Draft202012Validator(schema).iter_errors(bad))
    assert len(errs) > 0


# ── PR #704 P2 정정 회귀 (2건) — label_status enum 확장 ──────────────────

def test_schema_accepts_label_status_approved(schema, gold_item_with_text):
    """label_status=approved → schema valid (reviewer 필수)."""
    item = deepcopy(gold_item_with_text)
    item["label_status"] = "approved"
    # gold_item_with_text 에 reviewer 가 있음 → G9 conditional 통과
    errs = list(Draft202012Validator(schema).iter_errors(item))
    assert errs == [], f"unexpected errors: {[e.message for e in errs]}"


def test_schema_accepts_label_status_gold_v1(schema, gold_item_with_text):
    """label_status=gold_v1 → schema valid (reviewer 필수)."""
    item = deepcopy(gold_item_with_text)
    item["label_status"] = "gold_v1"
    errs = list(Draft202012Validator(schema).iter_errors(item))
    assert errs == [], f"unexpected errors: {[e.message for e in errs]}"
