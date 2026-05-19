"""test_slot_integrity.py — D-4 Card 2 M-52 슬롯 불변식 6건 (M-60 신규).

M-52: "출처 없는 것을 잘 비워두기" — source_fact / citation 없으면 confidence
무관 blank.
"""
from __future__ import annotations

from butler_pc_core.router.card2_routing import DeviceState, choose_card2_mapping_model
from butler_pc_core.cards.document_transform.mapper import (
    SourceFact, TemplateSlot, classify_slot_fill, map_facts_to_template_slots,
)

_ROUTING_SM = choose_card2_mapping_model("S", DeviceState(measured=True))


def test_no_source_fact_forces_blank_even_confidence_100():
    """HOLD_02 — source_fact_id 부재 시 confidence 1.0 이어도 blank."""
    assert classify_slot_fill(1.0, _ROUTING_SM, source_fact_id=None,
                              citation="c1") == "blank"


def test_no_citation_forces_blank_even_confidence_100():
    """HOLD_03 — citation 부재 시 confidence 1.0 이어도 blank."""
    assert classify_slot_fill(1.0, _ROUTING_SM, source_fact_id="f1",
                              citation=None) == "blank"


def test_factpack_fail_forces_blank():
    assert classify_slot_fill(1.0, _ROUTING_SM, source_fact_id="f1",
                              citation="c1", factpack_ok=False) == "blank"


def test_low_confidence_forces_blank():
    assert classify_slot_fill(0.50, _ROUTING_SM, source_fact_id="f1",
                              citation="c1") == "blank"


def test_high_confidence_with_full_provenance_auto_fills():
    assert classify_slot_fill(0.95, _ROUTING_SM, source_fact_id="f1",
                              citation="c1") == "auto_fill"


def test_map_facts_blank_slot_has_no_source_fact_id():
    slots = [TemplateSlot(slot_id="revenue", heading="매출 revenue", expected_type="money")]
    facts = [SourceFact(fact_id="f1", label="비용 cost", value="", value_type="text",
                        citation=None)]
    mappings = map_facts_to_template_slots(facts, slots, _ROUTING_SM)
    m = mappings[0]
    assert m.decision == "blank"
    assert m.source_fact_id is None or m.citation is None
