from __future__ import annotations

from butler.card5.alias_map import apply_alias


def test_apply_alias_title_code_returns_3_tuple():
    result = apply_alias("통신비", "0000")
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert result == ("통신비", "8080", "exact")


def test_apply_alias_service_sales_returns_3_tuple():
    result = apply_alias("서비스매출", "9999")
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert result == ("용역매출", "4040", "alias_mapped")


def test_apply_alias_dict_still_returns_dict():
    result = apply_alias({"account_title": "통신비", "account_code": "0000"})
    assert isinstance(result, dict)
    assert result["account_title"] == "통신비"


def test_apply_alias_description_dict_still_returns_dict():
    result = apply_alias(
        "일시 임대료수익 정산",
        {"account_title": "임대수입", "account_code": "4050"},
    )
    assert isinstance(result, dict)
    assert result["account_title"] == "임대료수익"
    assert result["account_code"] == "9040"


def test_apply_alias_all_v3_patterns_remain_supported():
    assert isinstance(apply_alias({"account_title": "통신비", "account_code": "8080"}), dict)
    assert isinstance(
        apply_alias(
            {"account_title": "임대매출", "account_code": "4050"},
            description="보유 장비 임대 매출 입금 alias case",
        ),
        dict,
    )
    assert isinstance(
        apply_alias(
            description="일시 임대료수익 정산",
            prediction={"account_title": "임대수입", "account_code": "4050"},
        ),
        dict,
    )
    assert isinstance(
        apply_alias("일시 임대료수익 정산", {"account_title": "임대수입", "account_code": "4050"}),
        dict,
    )
    assert len(apply_alias("통신비", "0000")) == 3

