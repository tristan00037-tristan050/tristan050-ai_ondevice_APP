"""test_score_tie.py — 동점 raw score 시 keyword 계정이 vendor-only를 이겨야 한다."""
from __future__ import annotations

import pytest

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

_skip = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")


def test_score_tie_keyword_wins_over_vendor_only():
    """동점(raw=1.0) 시 vendor-only(conf=0.30)보다 keyword 계정(conf≥0.50)이 선택돼야 한다.

    재현 경로:
    - 통신비(ACCOUNTS): KT + SKT vendor 각 1회 매칭 → raw=1.0, conf=0.30
    - 지급임차료(ACCOUNTS): "지급임차료" keyword 매칭 → raw=1.0, conf≥0.50
    - 수정 전: 통신비가 먼저 잠겨 conf<0.50 → 미분류 반환 (버그)
    - 수정 후: 동점에서 conf 높은 지급임차료 선택 → 지급임차료, conf≥0.50
    """
    from butler_pc_core.accounting.account_dict import match_account

    name, conf = match_account("KT SKT 지급임차료 납부", "")
    assert name == "지급임차료", (
        f"동점 처리 실패 — 기대: '지급임차료', 실제: '{name}' "
        f"(vendor-only 계정이 keyword 계정을 잠금)"
    )
    assert conf >= 0.50, f"keyword 계정 신뢰도 {conf:.0%} < 50%"


@_skip
def test_score_tie_reflected_in_classify_df():
    """동점 시나리오가 classify_df() 레벨에서도 올바르게 분류되는지 확인."""
    from butler_pc_core.accounting.classifier import classify_df

    df = pd.DataFrame([
        {"적요": "KT SKT 지급임차료 납부", "거래처": ""},
        {"적요": "KT 보험료납부 처리", "거래처": "SKT"},
    ])
    result = classify_df(df)

    assert result.iloc[0]["분류과목"] == "지급임차료", (
        f"행 0 분류 실패: {result.iloc[0]['분류과목']}"
    )
    assert result.iloc[1]["분류과목"] == "보험료", (
        f"행 1 분류 실패: {result.iloc[1]['분류과목']}"
    )
    assert (result["신뢰도"] >= 0.50).all(), (
        f"신뢰도 50% 미만:\n{result[['적요', '분류과목', '신뢰도']].to_string()}"
    )
