from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from butler_pc_core.accounting.policy import Money, PolicyLoadError, parse_krw, source_text_sha256


@pytest.mark.parametrize(
    ("text", "minor_units"),
    [("0", 0), ("1,234", 1234), ("-500", -500), (" 30000000 ", 30_000_000)],
)
def test_parse_krw_exact_minor_units(text: str, minor_units: int) -> None:
    money = parse_krw(text, digest=source_text_sha256(text))
    assert money == Money("KRW", minor_units, source_text_sha256(text))


@pytest.mark.parametrize("text", ["1.1", "NaN", "Infinity", "1e3", "12,34", "", "  "])
def test_parse_krw_rejects_ambiguous_or_fractional_text(text: str) -> None:
    with pytest.raises(PolicyLoadError):
        parse_krw(text, digest=source_text_sha256(text))


def test_parse_krw_binds_original_text_digest() -> None:
    with pytest.raises(PolicyLoadError, match="^MONEY:SOURCE_DIGEST_MISMATCH$"):
        parse_krw("1000", digest=source_text_sha256("1,000"))


def test_money_rejects_bool_minor_units() -> None:
    with pytest.raises(PolicyLoadError, match="^MONEY:NOT_INTEGER_MINOR_UNITS$"):
        Money("KRW", True, "0" * 64)


def test_money_is_immutable() -> None:
    money = Money("KRW", 100, "0" * 64)
    with pytest.raises(FrozenInstanceError):
        money.minor_units = 200
