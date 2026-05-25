from __future__ import annotations

from butler.card5.alias_map import apply_canonical_alias_map


def test_alias_map_swap_changes_prediction():
    description = "외주 용역료 지급"
    prediction = {"account_title": "용역비", "account_code": "9999", "category": "expense"}

    alias_map_v1 = {
        "aliases": {
            "외주": {
                "account_title": "외주용역비",
                "account_code": "8100",
                "category": "sga",
                "reason": "외주 → 8100",
            }
        }
    }
    alias_map_v2 = {
        "aliases": {
            "외주": {
                "account_title": "외주용역비",
                "account_code": "8200",
                "category": "sga",
                "reason": "외주 → 8200",
            }
        }
    }

    result_v1 = apply_canonical_alias_map(description, prediction, alias_map_v1)
    result_v2 = apply_canonical_alias_map(description, prediction, alias_map_v2)

    assert result_v1["account_code"] == "8100"
    assert result_v2["account_code"] == "8200"
    assert result_v1["account_code"] != result_v2["account_code"]
    assert result_v1["alias_map_applied"] is True
    assert result_v2["alias_map_applied"] is True


def test_alias_map_default_when_none():
    description = "외주 용역료 지급"
    prediction = {"account_title": "용역비", "account_code": "9999", "category": "expense"}

    result_none = apply_canonical_alias_map(description, prediction, None)
    result_omit = apply_canonical_alias_map(description, prediction)

    assert result_none == result_omit
    assert result_none["alias_map_applied"] is False


def test_alias_map_does_not_override_rent_precedence():
    description = "임대료수익 정산"
    prediction = {"account_title": "임대수입", "account_code": "4050"}

    alias_map = {
        "aliases": {
            "임대료수익": {
                "account_title": "X",
                "account_code": "0000",
                "category": "x",
            }
        }
    }
    result = apply_canonical_alias_map(description, prediction, alias_map)

    assert result["account_title"] == "임대료수익"
    assert result["account_code"] == "9040"
    assert result["alias_map_applied"] is True
