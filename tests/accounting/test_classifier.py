"""test_classifier.py — 분류 정확도 90% 이상 검증."""
from __future__ import annotations

import pytest

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

from .conftest import make_synthetic_df, _skip_no_pandas


@_skip_no_pandas
def test_accuracy_above_90():
    """합성 100건 데이터 분류 정확도 ≥ 90%."""
    from butler_pc_core.accounting.classifier import classify_df

    df = make_synthetic_df(100)
    result = classify_df(df)

    assert "분류과목" in result.columns
    assert "신뢰도" in result.columns
    assert len(result) == 100

    correct = (result["분류과목"] == df["expected"]).sum()
    accuracy = correct / len(df)

    assert accuracy >= 0.90, (
        f"분류 정확도 {accuracy:.1%} < 90%\n"
        f"오분류 샘플:\n"
        + result[result["분류과목"] != df["expected"]][
            ["적요", "거래처", "분류과목", "expected"]
        ].to_string()
    )


@_skip_no_pandas
def test_unclassified_column_present():
    """미분류 항목 컬럼 존재 + 신뢰도=0.0 검증."""
    from butler_pc_core.accounting.classifier import classify_df

    df = pd.DataFrame([{"적요": "알수없는 항목 xyz", "거래처": ""}])
    result = classify_df(df)

    assert result.iloc[0]["분류과목"] == "미분류"
    assert result.iloc[0]["신뢰도"] == 0.0


@_skip_no_pandas
def test_confidence_range():
    """신뢰도 값 범위 0.0~1.0 검증."""
    from butler_pc_core.accounting.classifier import classify_df

    df = make_synthetic_df(50)
    result = classify_df(df)

    assert (result["신뢰도"] >= 0.0).all(), "신뢰도 음수 발견"
    assert (result["신뢰도"] <= 1.0).all(), "신뢰도 1.0 초과 발견"


@_skip_no_pandas
def test_vendor_pattern_assists_classification():
    """거래처명 패턴이 분류에 기여하는지 검증."""
    from butler_pc_core.accounting.classifier import classify_df

    df = pd.DataFrame([
        {"적요": "전기요금 납부", "거래처": "한전"},
        {"적요": "화재보험 납부", "거래처": "삼성화재"},
        {"적요": "주유비 지급", "거래처": "SK에너지"},
    ])
    result = classify_df(df)

    assert result.iloc[0]["분류과목"] == "전력비"
    assert result.iloc[1]["분류과목"] == "보험료"
    assert result.iloc[2]["분류과목"] == "차량유지비"


@_skip_no_pandas
def test_output_is_copy_not_mutation():
    """classify_df가 원본 DataFrame을 변경하지 않는지 검증."""
    from butler_pc_core.accounting.classifier import classify_df

    df = make_synthetic_df(10)
    original_cols = list(df.columns)
    classify_df(df)

    assert list(df.columns) == original_cols, "원본 DataFrame 컬럼이 변경됨"
    assert "분류과목" not in df.columns
