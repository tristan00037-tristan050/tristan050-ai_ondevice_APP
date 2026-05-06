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
    """분류 결과를 3시트 xlsx로 저장.

    [분류결과] 원본 컬럼 + 분류과목 + 신뢰도(정수%)  — 분류 성공 행만
    [요약]    분류과목 | 건수 | 합계 | 평균
    [미분류]  원본 컬럼만  — 분류 실패 행
    """
    if not _PANDAS_OK:
        raise ImportError("pandas가 설치되지 않았습니다.")
    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError as exc:
        raise RuntimeError("openpyxl 미설치 — pip install openpyxl") from exc

    orig_cols = [c for c in df.columns if c not in ("분류과목", "신뢰도")]
    df_ok = df[df["분류과목"] != "미분류"].copy()
    df_ng = df[df["분류과목"] == "미분류"][orig_cols].copy()
    bold = Font(bold=True)

    wb = openpyxl.Workbook()

    # ── [분류결과] ──────────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "분류결과"
    ws1.append(orig_cols + ["분류과목", "신뢰도"])
    for cell in ws1[1]:
        cell.font = bold
    for _, row in df_ok.iterrows():
        vals = [row[c] for c in orig_cols]
        vals.append(row["분류과목"])
        vals.append(f"{int(round(float(row['신뢰도']) * 100))}%")
        ws1.append(vals)

    # ── [요약] ──────────────────────────────────────────────────────────────
    ws2 = wb.create_sheet("요약")
    ws2.append(["분류과목", "건수", "합계", "평균"])
    for cell in ws2[1]:
        cell.font = bold
    amount_col = _detect_col(list(df.columns), _AMOUNT_CANDIDATES)
    if amount_col and not df_ok.empty:
        df_ok["_amt"] = pd.to_numeric(df_ok[amount_col], errors="coerce").fillna(0)
        grp = df_ok.groupby("분류과목")["_amt"].agg(["count", "sum", "mean"]).reset_index()
        for _, r in grp.iterrows():
            ws2.append([r["분류과목"], int(r["count"]), int(r["sum"]), int(r["mean"])])
        t_cnt = int(grp["count"].sum())
        t_sum = int(grp["sum"].sum())
        ws2.append(["총계", t_cnt, t_sum, int(t_sum / t_cnt) if t_cnt else 0])
    elif not df_ok.empty:
        grp = df_ok.groupby("분류과목").size().reset_index(name="count")
        for _, r in grp.iterrows():
            ws2.append([r["분류과목"], int(r["count"]), 0, 0])
        ws2.append(["총계", int(grp["count"].sum()), 0, 0])

    # ── [미분류] ────────────────────────────────────────────────────────────
    ws3 = wb.create_sheet("미분류")
    ws3.append(orig_cols)
    for cell in ws3[1]:
        cell.font = bold
    for _, row in df_ng.iterrows():
        ws3.append([row[c] for c in orig_cols])

    wb.save(str(out_path))
