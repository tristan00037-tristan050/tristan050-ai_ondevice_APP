"""test_card2_routing.py — D-4 Card 2 라우팅 7건 (M-60 신규 작성)."""
from __future__ import annotations

from butler_pc_core.router.card2_routing import (
    DeviceState, classify_card2_tier, choose_card2_mapping_model,
    measure_device_state, audit_card2_routing_decision,
)
from butler_pc_core.cards.document_transform.mapper import classify_slot_fill

_GOOD_L = DeviceState(is_m3_max=True, free_ram_gb=8.0, battery_percent=80,
                      thermal_state="nominal", measured=True)
_BAD_L = DeviceState(is_m3_max=True, free_ram_gb=4.0, battery_percent=80,
                     thermal_state="nominal", measured=True)


def test_tier_classification_boundaries():
    assert classify_card2_tier(1024) == "S"
    assert classify_card2_tier(200 * 1024) == "M"
    assert classify_card2_tier(2 * 1024 * 1024) == "L"
    assert classify_card2_tier(8 * 1024 * 1024) == "XL"


def test_xl_tier_is_blocked():
    d = choose_card2_mapping_model("XL", _GOOD_L)
    assert d.model == "blocked" and d.auto_fill_allowed is False


def test_sm_routes_to_1_7b_autofill_allowed():
    for tier in ("S", "M"):
        d = choose_card2_mapping_model(tier, _GOOD_L)
        assert d.model == "butler-1.7b-q4_k_m"
        assert d.auto_fill_allowed is True
        assert d.threshold_auto_fill == 0.82


def test_l_gate_pass_routes_to_4b():
    d = choose_card2_mapping_model("L", _GOOD_L)
    assert d.model == "qwen3-4b-q4_k_m"
    assert d.auto_fill_allowed is True and d.threshold_auto_fill == 0.85
    assert d.gate_failures == ()


def test_l_gate_fail_falls_back_to_1_7b():
    d = choose_card2_mapping_model("L", _BAD_L)
    assert d.model == "butler-1.7b-q4_k_m"
    assert d.auto_fill_allowed is False
    assert d.threshold_auto_fill is None
    assert "free_ram<6.0" in d.gate_failures


def test_17b_l_fallback_never_auto_fills():
    """HOLD_05 — 1.7B L fallback 은 confidence 1.0 이어도 auto_fill 불가."""
    d = choose_card2_mapping_model("L", _BAD_L)
    out = classify_slot_fill(1.0, d, source_fact_id="f1", citation="c1",
                             factpack_ok=True)
    assert out == "review", f"fallback 이 auto_fill 함: {out}"


def test_audit_record_meta_only_no_raw():
    d = choose_card2_mapping_model("L", _GOOD_L)
    rec = audit_card2_routing_decision(d, 2 * 1024 * 1024, _GOOD_L)
    assert rec["model"] == "qwen3-4b-q4_k_m"
    assert "measured_at" in rec and rec["evidence_kind"] == "real_run"
    for forbidden in ("raw_text", "source_text", "raw_paragraph"):
        assert forbidden not in rec
