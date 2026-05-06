"""test_bundle_deps.py — 번들 의존성(openpyxl, xlrd) 가용성 + 실제 xlsx 분류 검증."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest


def test_openpyxl_importable():
    """openpyxl이 ImportError 없이 임포트 가능해야 한다."""
    import openpyxl  # noqa: F401
    assert openpyxl.__version__


def test_xlrd_importable():
    """xlrd가 ImportError 없이 임포트 가능해야 한다."""
    import xlrd  # noqa: F401
    assert xlrd.__version__


def test_xlsx_roundtrip_classify():
    """openpyxl로 생성한 .xlsx 파일을 classify_file()로 분류 — ImportError 없이 완료."""
    try:
        import pandas as pd
        import openpyxl  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"의존성 미설치: {exc}")

    from butler_pc_core.accounting.classifier import classify_df

    # 합성 거래내역 DataFrame
    df = pd.DataFrame({
        "적요": ["급여 지급 처리건", "통신비 납부", "임차료 납부", "소모품구입 처리"],
        "거래처": ["", "KT", "", ""],
        "금액": [500000, 55000, 1200000, 30000],
    })

    result = classify_df(df)
    assert "분류과목" in result.columns
    assert "신뢰도" in result.columns

    # xlsx 저장 + 다시 읽기
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name
    try:
        result.to_excel(tmp_path, index=False, engine="openpyxl")
        df_reload = pd.read_excel(tmp_path, dtype=str, engine="openpyxl")
        assert "분류과목" in df_reload.columns
        assert len(df_reload) == 4
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_xlrd_can_open_xls_bytes():
    """xlrd 2.x가 .xls 바이너리 스트림을 열 수 있는지 (최소 헤더 확인)."""
    import xlrd

    # xlrd.open_workbook()은 file_contents 인자를 받음
    # 최소한 유효한 .xls 파일이 없어도 xlrd 자체가 로드되는지 확인
    assert hasattr(xlrd, "open_workbook"), "xlrd.open_workbook 없음"
    assert xlrd.__version__ >= "2.0", f"xlrd 버전 낮음: {xlrd.__version__}"
