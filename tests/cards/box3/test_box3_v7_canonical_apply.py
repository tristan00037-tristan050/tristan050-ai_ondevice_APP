
def test_track1_date_four_formats_supported():
    from butler_pc_core.cards.box3.sdk.helper4_grounding_sdk import _facts, _facts_supported
    ev = _facts("납품 일정: 2026년 6월 10일 (목요일)")
    for c in ["2026년 6월 10일", "2026-06-10", "2026.06.10", "2026/06/10"]:
        assert _facts_supported(_facts(c), ev), c

def test_track1_month_partial_not_dateoverride():
    from butler_pc_core.cards.box3.sdk.helper4_grounding_sdk import _facts, _facts_supported
    assert _facts_supported(_facts("6월 15일 진행"), _facts("진행 시기: 2026년 6월")) is False
    assert _facts_supported(_facts("6월 중 진행"), _facts("2026년 6월 10일 납품")) is True
    assert _facts_supported(_facts("7월 중 진행"), _facts("2026년 6월 10일 납품")) is False

def test_track1_qty_comma_normalized():
    from butler_pc_core.cards.box3.sdk.helper4_grounding_sdk import _facts, _facts_supported
    assert _facts_supported(_facts("비용 1,000원"), _facts("추가 비용: 1000원")) is True
