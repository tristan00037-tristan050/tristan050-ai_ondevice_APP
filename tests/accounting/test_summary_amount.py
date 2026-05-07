"""test_summary_amount.py — build_summary에 total_amount 포함 검증."""
from __future__ import annotations

import pytest

from .conftest import make_synthetic_df, make_comma_amount_df, _skip_no_pandas


@_skip_no_pandas
def test_build_summary_categories_have_total_amount_key():
    """build_summary 각 카테고리에 total_amount 키 포함 검증."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary

    df = make_synthetic_df(50)
    result = classify_df(df)
    summary = build_summary(result)

    assert "categories" in summary
    for cat_name, cat_info in summary["categories"].items():
        assert "total_amount" in cat_info, f"카테고리 '{cat_name}'에 total_amount 키 없음"
        assert isinstance(cat_info["total_amount"], int), (
            f"카테고리 '{cat_name}'.total_amount가 int가 아님: {type(cat_info['total_amount'])}"
        )


@_skip_no_pandas
def test_build_summary_total_amount_zero_without_amt_column():
    """_amt 컬럼 없을 때 total_amount=0 반환 검증."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary

    # make_synthetic_df는 단일 '금액' 컬럼만 있어 _amt 컬럼 미생성
    df = make_synthetic_df(20)
    result = classify_df(df)
    assert "_amt" not in result.columns, "_amt 컬럼이 없어야 함 (단일 금액 컬럼만 존재)"

    summary = build_summary(result)
    for cat_name, cat_info in summary["categories"].items():
        assert cat_info["total_amount"] == 0, (
            f"_amt 없을 때 '{cat_name}'.total_amount={cat_info['total_amount']} (0 기대)"
        )


@_skip_no_pandas
def test_build_summary_total_amount_with_amt_column():
    """_amt 컬럼 존재 시 total_amount가 0이 아닌 값 포함 검증."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary

    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas 미설치")

    # 입출금 분리 컬럼 포함 DataFrame → classify_df가 _amt 계산
    rows = [
        {"적요": "급여 지급",    "거래처": "",   "출금": "3200000", "입금": ""},
        {"적요": "통신비 납부",  "거래처": "KT", "출금": "88000",   "입금": ""},
        {"적요": "이자수익 입금","거래처": "",   "출금": "",        "입금": "50000"},
    ]
    df = pd.DataFrame(rows).fillna("")
    result = classify_df(df)

    assert "_amt" in result.columns, "_amt 컬럼이 있어야 함 (입출금 분리 컬럼 존재)"

    summary = build_summary(result)
    non_zero = [
        cat for cat, info in summary["categories"].items()
        if info.get("total_amount", 0) != 0
    ]
    assert len(non_zero) > 0, (
        f"_amt 컬럼 존재 시 total_amount != 0인 카테고리가 있어야 함 — 전부 0: {summary['categories']}"
    )
