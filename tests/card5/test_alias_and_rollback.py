import pytest

from butler.card5.alias_map import apply_alias
from butler.card5.rollback import InferenceResult, check_and_rollback


def test_exact_allowlist_title_passes():
    title, code, kind = apply_alias("통신비", "0000")
    assert title == "통신비"
    assert code == "8080"
    assert kind == "exact"


def test_alias_maps_to_allowlist_code():
    title, code, kind = apply_alias("서비스매출", "9999")
    assert title == "용역매출"
    assert code == "4040"
    assert kind == "alias_mapped"


def test_hallucination_rolls_back():
    result = InferenceResult(
        account_title="매출 수익",
        account_code="50",
        needs_review=False,
        match_kind="hallucination",
        confidence=0.99,
    )
    out = check_and_rollback(result)
    assert out.needs_review is True
    assert out.rollback_triggered is True
    assert out.rollback_reason
