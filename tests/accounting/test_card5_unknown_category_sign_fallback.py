"""test_card5_unknown_category_sign_fallback.py — Codex P2 보완 검증.

결함: build_summary()의 sign fallback 기본값이 "+"라서, 사전
(ACCOUNT_BY_NAME)에 없는 카테고리(PEFT 모델 반환 등)를 자동으로
[수익]으로 오표시할 위험이 있었다.

수정: acc is None일 때 _amt 순액 부호로 sign/section 을 추론한다.
사전에 있는 카테고리는 기존 acc.sign/section 을 그대로 유지한다.

검증 데이터는 통장샘플.csv 원본이 아닌 합성 분류 결과다.
"""
from __future__ import annotations

import pytest

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

_skip = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")


def _summary(rows: list[dict]):
    from butler_pc_core.accounting.report import build_summary
    return build_summary(pd.DataFrame(rows))


# ── 시나리오 1: 사전 미등록 카테고리 + 음수 amount → 비용 ────────────────────
@_skip
def test_unknown_category_negative_amount_inferred_as_expense():
    cats = _summary([
        {"분류과목": "미등록비용계정", "신뢰도": 0.85, "_amt": -120000},
    ])["categories"]
    assert cats["미등록비용계정"]["sign"] == "-", "음수 순액 → sign 비용(-) 추론 실패"
    assert cats["미등록비용계정"]["section"] == "expense"


# ── 시나리오 2: 사전 미등록 카테고리 + 양수 amount → 수익 ────────────────────
@_skip
def test_unknown_category_positive_amount_inferred_as_revenue():
    cats = _summary([
        {"분류과목": "미등록수익계정", "신뢰도": 0.85, "_amt": 450000},
    ])["categories"]
    assert cats["미등록수익계정"]["sign"] == "+", "양수 순액 → sign 수익(+) 추론 실패"
    assert cats["미등록수익계정"]["section"] == "revenue"


# ── 시나리오 3: 사전 등록 카테고리는 acc.sign/section 유지 ───────────────────
@_skip
def test_known_category_keeps_account_dict_metadata():
    cats = _summary([
        {"분류과목": "매출", "신뢰도": 0.90, "_amt": 1000000},
        {"분류과목": "통신비", "신뢰도": 0.90, "_amt": -90000},
    ])["categories"]
    # 사전 메타가 _amt 추론(revenue/expense)이 아닌 account_dict 값으로 유지
    assert cats["매출"]["sign"] == "+" and cats["매출"]["section"] == "I_revenue"
    assert cats["통신비"]["sign"] == "-" and cats["통신비"]["section"] == "IV_sga"


# ── 시나리오 4: 미분류는 categories 에서 격리 유지 ───────────────────────────
@_skip
def test_unclassified_row_isolated_from_categories():
    summary = _summary([
        {"분류과목": "미분류", "신뢰도": 0.0, "_amt": -50000},
        {"분류과목": "통신비", "신뢰도": 0.90, "_amt": -90000},
    ])
    assert "미분류" not in summary["categories"], "미분류가 categories 에 노출됨"
    assert summary["unclassified_rows"] == 1
    assert summary["classified_rows"] == 1
