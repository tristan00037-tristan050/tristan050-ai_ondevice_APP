"""test_determinism.py — 동일 입력 10회 반복 → 100% 동일 출력 검증."""
from __future__ import annotations

import pytest

from .conftest import make_synthetic_df, _skip_no_pandas


@_skip_no_pandas
def test_determinism_10_runs():
    """동일 DataFrame 10회 분류 → 모든 결과 동일."""
    from butler_pc_core.accounting.classifier import classify_df

    df = make_synthetic_df(100)
    results = [classify_df(df)["분류과목"].tolist() for _ in range(10)]

    for i, r in enumerate(results[1:], 1):
        assert r == results[0], f"실행 {i+1}회 결과가 첫 실행과 다름"


@_skip_no_pandas
def test_determinism_confidence_stable():
    """신뢰도 값도 10회 실행 동일."""
    from butler_pc_core.accounting.classifier import classify_df

    df = make_synthetic_df(50)
    results = [classify_df(df)["신뢰도"].tolist() for _ in range(10)]

    for i, r in enumerate(results[1:], 1):
        assert r == results[0], f"실행 {i+1}회 신뢰도가 첫 실행과 다름"


@_skip_no_pandas
def test_determinism_single_row():
    """단일 행 10회 분류 → 동일 계정과목."""
    from butler_pc_core.accounting.classifier import classify_df
    import pandas as pd

    df = pd.DataFrame([{"적요": "급여 지급 처리건", "거래처": ""}])
    results = [classify_df(df)["분류과목"].iloc[0] for _ in range(10)]

    assert len(set(results)) == 1, f"단일 행 결과 불일치: {set(results)}"
    assert results[0] == "직원급여"
