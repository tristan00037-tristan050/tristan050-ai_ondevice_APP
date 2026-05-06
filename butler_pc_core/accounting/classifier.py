"""결정적 분류 엔진 — 동일 입력 10회 반복 → 100% 동일 출력."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Union

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

from .account_dict import match_account

# 설명 컬럼 후보 (우선순위순)
_DESC_CANDIDATES = [
    "적요", "내용", "거래내용", "description", "memo", "摘要", "비고", "내역",
    "거래적요", "이체메모", "출금내역", "입금내역",
]
# 거래처 컬럼 후보
_VENDOR_CANDIDATES = [
    "거래처", "상호", "vendor", "payee", "대상", "상대방", "입금처", "출금처",
]
# 금액 컬럼 후보
_AMOUNT_CANDIDATES = [
    "금액", "출금액", "입금액", "amount", "출금", "입금", "거래금액", "변동금액",
]


def _detect_col(columns: list[str], candidates: list[str]) -> str | None:
    """컬럼 목록에서 후보 중 첫 번째 일치 컬럼 반환."""
    col_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in columns:
            return cand
        if cand.lower() in col_lower:
            return col_lower[cand.lower()]
    return None


def _read_file(path: Union[str, Path]) -> "pd.DataFrame":
    """xlsx/csv/xls 자동 감지 후 DataFrame 로드."""
    if not _PANDAS_OK:
        raise ImportError("pandas가 설치되지 않았습니다. pip install pandas openpyxl")
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p, dtype=str).fillna("")
    elif suffix == ".csv":
        for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                return pd.read_csv(p, dtype=str, encoding=enc).fillna("")
            except UnicodeDecodeError:
                continue
        raise ValueError(f"CSV 인코딩을 감지할 수 없습니다: {p}")
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {suffix} (지원: .xlsx .xls .csv)")


def classify_df(df: "pd.DataFrame") -> "pd.DataFrame":
    """DataFrame에 [분류과목, 신뢰도] 컬럼을 추가해 반환.

    - 결정적: 동일 입력 → 동일 출력 (랜덤 없음)
    - 미분류 항목은 분류과목="미분류" 신뢰도=0.0
    """
    if not _PANDAS_OK:
        raise ImportError("pandas가 설치되지 않았습니다.")

    df = df.copy()
    columns = list(df.columns)

    desc_col = _detect_col(columns, _DESC_CANDIDATES)
    vendor_col = _detect_col(columns, _VENDOR_CANDIDATES)

    labels: list[str] = []
    confs: list[float] = []

    for _, row in df.iterrows():
        desc = str(row[desc_col]) if desc_col else ""
        vendor = str(row[vendor_col]) if vendor_col else ""
        name, conf = match_account(desc, vendor)
        labels.append(name)
        confs.append(conf)

    df["분류과목"] = labels
    df["신뢰도"] = confs
    return df


def classify_file(path: Union[str, Path]) -> "pd.DataFrame":
    """파일 경로 → 분류 결과 DataFrame."""
    df = _read_file(path)
    return classify_df(df)


def save_classified(df: "pd.DataFrame", out_path: Union[str, Path]) -> None:
    """분류 결과를 xlsx로 저장."""
    if not _PANDAS_OK:
        raise ImportError("pandas가 설치되지 않았습니다.")
    df.to_excel(str(out_path), index=False, engine="openpyxl")
