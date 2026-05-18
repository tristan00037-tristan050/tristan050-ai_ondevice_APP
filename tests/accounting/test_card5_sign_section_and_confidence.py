"""test_card5_sign_section_and_confidence.py — D-2 카드 5 GUI 결함 2건 검증.

결함 A: sign/section 메타가 결과에 노출되는지 (build_summary categories).
결함 B: 키워드 명중 분류의 신뢰도가 산출 공식 결함으로 50%대에 갇히지 않고
        설계 의도 상한(0.90+)에 도달하는지.

검증 데이터는 통장샘플.csv 원본이 아닌 합성 거래내역이다 (원본 데이터
외부 전송/저장 0 — Butler 핵심 원칙 정합).
"""
from __future__ import annotations

import pytest

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

_skip = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")


def _synthetic_bank_df() -> "pd.DataFrame":
    """합성 거래내역 7건 — 매출 2건(입금) + 비용 5종(출금). 원본 데이터 아님."""
    return pd.DataFrame([
        {"적요": "매출 입금",      "입금": "5000000", "출금": "0",       "거래처": ""},
        {"적요": "용역 매출 입금", "입금": "3000000", "출금": "0",       "거래처": ""},
        {"적요": "지급수수료 결제", "입금": "0",       "출금": "200000",  "거래처": ""},
        {"적요": "인건비 지급",    "입금": "0",       "출금": "2500000", "거래처": ""},
        {"적요": "사무용품 구입",  "입금": "0",       "출금": "150000",  "거래처": ""},
        {"적요": "임대료 납부",    "입금": "0",       "출금": "800000",  "거래처": ""},
        {"적요": "통신비 납부",    "입금": "0",       "출금": "90000",   "거래처": ""},
    ])


# ── 결함 B: 신뢰도 산출 공식 ─────────────────────────────────────────────────
def test_keyword_match_confidence_reaches_design_ceiling():
    """키워드 1건 명중 = 확정 분류 → 신뢰도 0.90 이상 (50%대 버그 해소)."""
    from butler_pc_core.accounting.account_dict import match_account

    for desc in ["통신비 납부", "사무용품 구입", "인건비 지급",
                  "임대료 납부", "지급수수료 결제", "매출 입금"]:
        name, conf = match_account(desc, "")
        assert name != "미분류", f"'{desc}' 미분류 — 분류 실패"
        assert conf >= 0.90, (
            f"'{desc}' → {name} 신뢰도 {conf:.0%} — 설계 의도 상한(90%) 미달"
        )


def test_vendor_only_match_still_isolated_below_threshold():
    """키워드 없이 벤더만 매칭 시 임계값(0.50) 미만 → 미분류 격리 유지."""
    from butler_pc_core.accounting.account_dict import match_account

    name, conf = match_account("정기 자동이체", "쿠팡")  # 쿠팡=소모품비 vendor
    assert name == "미분류" and conf == 0.0


@_skip
def test_confidence_no_longer_trapped_in_50s_band():
    """합성 거래 분류 결과 평균 신뢰도가 50%대(버그 증상)가 아니어야 한다."""
    from butler_pc_core.accounting.classifier import classify_df

    df = classify_df(_synthetic_bank_df())
    classified = df[df["분류과목"] != "미분류"]
    avg = float(classified["신뢰도"].mean())
    assert avg >= 0.90, f"평균 신뢰도 {avg:.1%} — 산출 공식 결함 잔존 (50%대 갇힘)"


# ── 결함 A: sign/section 메타 노출 ───────────────────────────────────────────
@_skip
def test_build_summary_exposes_sign_and_section():
    """build_summary categories 각 항목이 sign/section 메타를 포함해야 한다."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary
    from butler_pc_core.accounting.account_dict import SECTION_ORDER

    summary = build_summary(classify_df(_synthetic_bank_df()))
    cats = summary["categories"]
    assert len(cats) >= 6, f"계정과목 6개 이상 기대, 실제 {len(cats)}"
    for name, info in cats.items():
        assert info.get("sign") in ("+", "-"), f"'{name}' sign 메타 누락: {info}"
        assert info.get("section") in SECTION_ORDER, (
            f"'{name}' section 메타 누락/오류: {info}"
        )


@_skip
def test_revenue_categories_sort_to_top():
    """매출(I_revenue)이 재무제표 섹션 정렬에서 최상단이어야 한다 (검증 6-a)."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary
    from butler_pc_core.accounting.account_dict import SECTION_ORDER

    cats = build_summary(classify_df(_synthetic_bank_df()))["categories"]
    ordered = sorted(
        cats.items(),
        key=lambda kv: SECTION_ORDER.get(kv[1]["section"], 5),
    )
    assert ordered[0][0] == "매출", f"최상단이 매출이 아님: {ordered[0][0]}"
    assert cats["매출"]["count"] == 2, "매출 2건이 단일 계정과목으로 집계되어야 함"


@_skip
def test_expense_categories_have_negative_total_amount():
    """비용 계정 5종의 합계금액이 음수여야 한다 (검증 6-b — 음수 표시 정합)."""
    from butler_pc_core.accounting.classifier import classify_df
    from butler_pc_core.accounting.report import build_summary

    cats = build_summary(classify_df(_synthetic_bank_df()))["categories"]
    expenses = [n for n, i in cats.items() if i["sign"] == "-"]
    assert len(expenses) == 5, f"비용 계정 5종 기대, 실제 {len(expenses)}: {expenses}"
    for name in expenses:
        assert cats[name]["total_amount"] < 0, (
            f"비용 계정 '{name}' 합계금액이 음수가 아님: {cats[name]['total_amount']}"
        )
    assert cats["매출"]["total_amount"] > 0, "매출 합계금액은 양수여야 함"
