"""test_wiki_only_fact_not_autofillable.py — M-52 WIKI_ONLY fail class (M-60)."""
from __future__ import annotations

from butler_pc_core.router.card2_routing import DeviceState, choose_card2_mapping_model
from butler_pc_core.cards.document_transform.mapper import (
    SourceFact, TemplateSlot, map_facts_to_template_slots,
)


def test_wiki_only_fact_never_auto_fills():
    """원천 사실 부재·wiki 보조만인 사실은 confidence 무관 auto_fill 금지."""
    routing = choose_card2_mapping_model("S", DeviceState(measured=True))
    assert routing.auto_fill_allowed is True  # S tier — auto_fill 허용 경로
    slot = TemplateSlot(slot_id="market_tam", heading="시장 규모 market",
                        expected_type="money")
    wiki_fact = SourceFact(
        fact_id="w1", label="시장 규모 market", value="1조원",
        value_type="money", citation="wiki:Q123", wiki_only=True,
    )
    mappings = map_facts_to_template_slots([wiki_fact], [slot], routing)
    m = mappings[0]
    assert m.decision != "auto_fill", f"wiki-only 사실이 auto_fill 됨: {m.decision}"
    assert m.decision == "blank"
    assert m.fail_class == "WIKI_ONLY_FACT_NOT_AUTOFILLABLE"


def test_non_wiki_fact_can_auto_fill():
    """대조군 — wiki_only=False 정상 사실은 auto_fill 가능."""
    routing = choose_card2_mapping_model("S", DeviceState(measured=True))
    slot = TemplateSlot(slot_id="market_tam", heading="시장 규모 market",
                        expected_type="money")
    fact = SourceFact(fact_id="f1", label="시장 규모 market", value="1조원",
                      value_type="money", citation="ext:doc#2", wiki_only=False)
    m = map_facts_to_template_slots([fact], [slot], routing)[0]
    assert m.decision == "auto_fill"
