"""test_csv_direction_override.py — D-2 C 결함: CSV 입출금 분리 컬럼 → direction → _INCOME_OVERRIDE."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("ACCOUNTING_NO_PEFT", "1")

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

_skip = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")


def _df(*rows):
    return pd.DataFrame(rows)


@_skip
def test_csv_consulting_income_as_revenue():
    """입출금 분리 컬럼 + 자문 수입(입금) → 용역매출 / I_revenue."""
    from butler_pc_core.accounting.classifier import classify_df

    df = _df({"적요": "ABC컨설팅 자문 수입", "거래처": "ABC컨설팅", "출금": "", "입금": "5000000"})
    result = classify_df(df)
    assert result.iloc[0]["분류과목"] == "용역매출", f"분류과목={result.iloc[0]['분류과목']!r}"


@_skip
def test_csv_rental_income_as_non_op_revenue():
    """입출금 분리 컬럼 + 임대 수입(입금) → 임대수입 / VI_non_op_revenue."""
    from butler_pc_core.accounting.classifier import classify_df

    df = _df({"적요": "한국빌딩 임대 수입", "거래처": "한국빌딩", "출금": "", "입금": "3000000"})
    result = classify_df(df)
    assert result.iloc[0]["분류과목"] == "임대수입", f"분류과목={result.iloc[0]['분류과목']!r}"


@_skip
def test_csv_input_output_column_direction_correct():
    """출금 컬럼 비용 vs 입금 컬럼 수익 — 방향별 분류과목 상이 확인."""
    from butler_pc_core.accounting.classifier import classify_df

    df = _df(
        {"적요": "ABC컨설팅 자문료 송금", "거래처": "ABC컨설팅", "출금": "5000000", "입금": ""},
        {"적요": "ABC컨설팅 자문 수입", "거래처": "ABC컨설팅", "출금": "", "입금": "5000000"},
    )
    result = classify_df(df)
    expense_cat = result.iloc[0]["분류과목"]
    income_cat = result.iloc[1]["분류과목"]
    assert expense_cat == "지급수수료", f"출금 분류과목={expense_cat!r} (expected 지급수수료)"
    assert income_cat == "용역매출", f"입금 분류과목={income_cat!r} (expected 용역매출)"
    assert expense_cat != income_cat, "입금/출금이 동일하게 분류됨"
