"""test_mapping_confidence.py — D-4 Card 2 8요소 confidence 9건 (M-60 신규)."""
from __future__ import annotations

from butler_pc_core.cards.document_transform.mapper import (
    CONFIDENCE_WEIGHTS, SourceFact, TemplateSlot, compute_slot_confidence,
)

_SLOT = TemplateSlot(slot_id="revenue", heading="연 매출 revenue", expected_type="money")
_LEX = {"revenue": ["매출", "revenue"]}


def _fact(**kw):
    base = dict(fact_id="f1", label="연 매출 revenue", value="100", value_type="money",
                citation="ext:doc#3", factpack_ok=True, wiki_only=False, is_negated=False)
    base.update(kw)
    return SourceFact(**base)


def test_weights_sum_to_one():
    assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9


def test_eight_factors_present():
    _, factors = compute_slot_confidence(_fact(), _SLOT, _LEX)
    assert set(factors) == set(CONFIDENCE_WEIGHTS)
    assert len(factors) == 8


def test_none_fact_yields_zero_confidence():
    conf, factors = compute_slot_confidence(None, _SLOT, _LEX)
    assert conf == 0.0
    assert factors["source_fact_present"] == 0.0


def test_confidence_in_unit_range():
    conf, _ = compute_slot_confidence(_fact(), _SLOT, _LEX)
    assert 0.0 <= conf <= 1.0


def test_full_match_high_confidence():
    conf, _ = compute_slot_confidence(_fact(), _SLOT, _LEX)
    assert conf >= 0.85, f"완전 매칭 신뢰도 {conf}"


def test_citation_absent_lowers_confidence():
    with_c, _ = compute_slot_confidence(_fact(), _SLOT, _LEX)
    without_c, f = compute_slot_confidence(_fact(citation=None), _SLOT, _LEX)
    assert without_c < with_c
    assert f["citation_present"] == 0.0


def test_type_mismatch_lowers_confidence():
    match, _ = compute_slot_confidence(_fact(), _SLOT, _LEX)
    mismatch, f = compute_slot_confidence(_fact(value_type="text"), _SLOT, _LEX)
    assert mismatch < match and f["value_type_match"] == 0.0


def test_negation_factor():
    _, f = compute_slot_confidence(_fact(is_negated=True), _SLOT, _LEX)
    assert f["negation_free"] == 0.0


def test_lexicon_hit_factor():
    _, hit = compute_slot_confidence(_fact(), _SLOT, _LEX)
    _, miss = compute_slot_confidence(_fact(), _SLOT, lexicon={})
    assert hit["lexicon_hit"] == 1.0 and miss["lexicon_hit"] == 0.0
