"""test_multi_bank.py — 한국 6대 은행 export 형식 호환 검증 (+25 tests)."""
from __future__ import annotations

import pytest
from pathlib import Path

try:
    import pandas as pd
    import openpyxl
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_skip = pytest.mark.skipif(not _DEPS_OK, reason="pandas/openpyxl 미설치")

_BANKS_DIR = Path(__file__).parent.parent / "fixtures" / "banks"

# ─── 은행별 기대값 파라미터 ──────────────────────────────────────────────────
# (bank_id, filename, expected_header_row)
_HEADER_PARAMS = [
    ("ibk",     "ibk_sample.xlsx",     2),
    ("kb",      "kb_sample.xlsx",      4),
    ("shinhan", "shinhan_sample.xlsx", 0),
    ("woori",   "woori_sample.xlsx",   3),
    ("hana",    "hana_sample.xlsx",    5),
    ("nh",      "nh_sample.xlsx",      9),
]

# (bank_id, filename, expected_desc_col, expect_vendor)
_COLUMN_PARAMS = [
    ("ibk",     "ibk_sample.xlsx",     "거래내용",  True),
    ("kb",      "kb_sample.xlsx",      "거래내역",  True),
    ("shinhan", "shinhan_sample.xlsx", "적요",      True),
    ("woori",   "woori_sample.xlsx",   "적요",      True),
    ("hana",    "hana_sample.xlsx",    "적요",      True),
    ("nh",      "nh_sample.xlsx",      "거래내용",  False),
]

# (bank_id, filename, has_split_columns)
_SPLIT_PARAMS = [
    ("ibk",     "ibk_sample.xlsx",     True),
    ("kb",      "kb_sample.xlsx",      True),
    ("shinhan", "shinhan_sample.xlsx", False),
    ("woori",   "woori_sample.xlsx",   True),
    ("hana",    "hana_sample.xlsx",    False),
    ("nh",      "nh_sample.xlsx",      True),
]

# (bank_id, filename, min_classified_out_of_5)
_CLASSIFY_PARAMS = [
    ("ibk",     "ibk_sample.xlsx",     3),
    ("kb",      "kb_sample.xlsx",      4),
    ("shinhan", "shinhan_sample.xlsx", 4),
    ("woori",   "woori_sample.xlsx",   3),
    ("hana",    "hana_sample.xlsx",    4),
    ("nh",      "nh_sample.xlsx",      4),
]


# ─── 1. 헤더 자동 감지 (6 tests) ─────────────────────────────────────────────
@_skip
@pytest.mark.parametrize("bank_id,fname,expected_row", _HEADER_PARAMS,
                          ids=[p[0] for p in _HEADER_PARAMS])
def test_header_auto_detect_per_bank(bank_id, fname, expected_row):
    """각 은행 fixture에서 헤더 행 자동 감지가 정확해야 한다."""
    from butler_pc_core.accounting.classifier import _detect_header_row
    detected = _detect_header_row(_BANKS_DIR / fname)
    assert detected == expected_row, (
        f"[{bank_id}] 헤더 행 불일치 — 기대: {expected_row}, 감지: {detected}"
    )


# ─── 2. 컬럼명 패턴 매칭 (6 tests) ──────────────────────────────────────────
@_skip
@pytest.mark.parametrize("bank_id,fname,expected_desc,expect_vendor", _COLUMN_PARAMS,
                          ids=[p[0] for p in _COLUMN_PARAMS])
def test_column_pattern_match_per_bank(bank_id, fname, expected_desc, expect_vendor):
    """각 은행 fixture에서 적요/거래처 컬럼이 정확하게 감지돼야 한다."""
    from butler_pc_core.accounting.classifier import (
        _detect_header_row, _detect_col, _normalize_col,
        _DESC_CANDIDATES, _VENDOR_CANDIDATES,
    )
    header = _detect_header_row(_BANKS_DIR / fname)
    df = pd.read_excel(_BANKS_DIR / fname, header=header, dtype=str).fillna("")
    cols = list(df.columns)

    desc_col = _detect_col(cols, _DESC_CANDIDATES)
    vendor_col = _detect_col(cols, _VENDOR_CANDIDATES)

    assert _normalize_col(desc_col or "") == _normalize_col(expected_desc), (
        f"[{bank_id}] 적요 컬럼 불일치 — 기대: '{expected_desc}', 감지: '{desc_col}'"
    )
    if expect_vendor:
        assert vendor_col is not None, (
            f"[{bank_id}] 거래처 컬럼 감지 실패 (컬럼 목록: {cols})"
        )


# ─── 3. 입출금 분리 컬럼 → _amt (6 tests) ───────────────────────────────────
@_skip
@pytest.mark.parametrize("bank_id,fname,has_split", _SPLIT_PARAMS,
                          ids=[p[0] for p in _SPLIT_PARAMS])
def test_withdrawal_deposit_split_per_bank(bank_id, fname, has_split):
    """입출금 분리 컬럼이 있는 은행은 classify_df 후 _amt 컬럼이 생성돼야 한다."""
    from butler_pc_core.accounting.classifier import classify_file
    result = classify_file(_BANKS_DIR / fname)

    if has_split:
        assert "_amt" in result.columns, (
            f"[{bank_id}] 입출금 분리 감지 실패 — _amt 컬럼 없음 (컬럼: {list(result.columns)})"
        )
        # _amt 값이 수치형이고 0이 아닌 행 존재 확인
        classified = result[result["분류과목"] != "미분류"]
        assert (classified["_amt"].abs() > 0).any(), (
            f"[{bank_id}] _amt 값이 모두 0 — 콤마 파싱 실패"
        )
    else:
        assert "_amt" not in result.columns, (
            f"[{bank_id}] 단일 금액 컬럼임에도 _amt 생성됨"
        )


# ─── 4. 적요+거래처 결합 분류 (6 tests) ─────────────────────────────────────
@_skip
@pytest.mark.parametrize("bank_id,fname,min_classified", _CLASSIFY_PARAMS,
                          ids=[p[0] for p in _CLASSIFY_PARAMS])
def test_desc_vendor_combined_classify_per_bank(bank_id, fname, min_classified):
    """각 은행 fixture에서 KIFRS 분류 결과가 최소 기준 이상이어야 한다."""
    from butler_pc_core.accounting.classifier import classify_file
    result = classify_file(_BANKS_DIR / fname)

    classified = result[result["분류과목"] != "미분류"]
    assert len(classified) >= min_classified, (
        f"[{bank_id}] 분류 건수 부족 — 기대 ≥{min_classified}, 실제 {len(classified)}/5\n"
        + result[["분류과목", "신뢰도"]].to_string()
    )
    assert (classified["신뢰도"] >= 0.50).all(), (
        f"[{bank_id}] 신뢰도 50% 미만 발견\n"
        + classified[["분류과목", "신뢰도"]].to_string()
    )


# ─── 5. 농협 거래일자+거래시간 결합 (1 test) ─────────────────────────────────
@_skip
def test_nh_date_time_merge():
    """농협 fixture는 거래일자+거래시간이 결합된 _datetime 컬럼이 생성돼야 한다."""
    from butler_pc_core.accounting.classifier import classify_file
    result = classify_file(_BANKS_DIR / "nh_sample.xlsx")

    assert "_datetime" in result.columns, (
        f"NH _datetime 컬럼 미생성 (컬럼: {list(result.columns)})"
    )
    # _datetime = 거래일자 + 거래시간 결합 형식 확인
    sample = result["_datetime"].iloc[0]
    assert " " in str(sample), (
        f"_datetime 형식이 'YYYY-MM-DD HH:MM:SS' 패턴이 아님: '{sample}'"
    )
    # NH도 분류 정상 작동 확인
    classified = result[result["분류과목"] != "미분류"]
    assert len(classified) >= 4, (
        f"NH 분류 건수 부족: {len(classified)}/5"
    )
