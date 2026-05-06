"""test_sme_accounts.py — 중소기업회계기준 32개 계정과목 사전 검증 (+5 tests)."""
from __future__ import annotations

import pytest

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

_skip = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")

# ── 1. 32개 계정과목 등록 확인 ──────────────────────────────────────────────
def test_sme_32_accounts_registered():
    """중소기업회계기준 표준 계정과목 32개가 모두 등록돼야 한다 (미분류 제외)."""
    from butler_pc_core.accounting.account_dict import ACCOUNTS

    real_accounts = [a for a in ACCOUNTS if a.name != "미분류"]
    assert len(real_accounts) == 32, (
        f"계정과목 수 불일치 — 기대: 32, 실제: {len(real_accounts)}\n"
        f"등록된 계정: {[a.name for a in real_accounts]}"
    )

    # 필수 계정과목 존재 확인
    names = {a.name for a in real_accounts}
    required = {
        "매출", "상품매출원가", "매출총이익",
        "임원급여", "직원급여", "상여금", "퇴직급여",
        "복리후생비", "여비교통비", "접대비", "통신비", "전력비",
        "세금과공과금", "감가상각비", "지급임차료", "보험료", "차량유지비",
        "경상연구개발비", "운반비", "교육훈련비", "도서인쇄비",
        "사무용품비", "소모품비", "지급수수료", "광고선전비", "건물관리비",
        "이자수익", "유형자산처분이익", "잡이익",
        "이자비용", "전기오류수정손실", "잡손실",
    }
    missing = required - names
    assert not missing, f"누락된 계정과목: {missing}"


# ── 2. 인건비 4분리 분류 정확도 ──────────────────────────────────────────────
def test_payroll_four_way_split():
    """임원급여·직원급여·상여금·퇴직급여가 각각 정확히 분류돼야 한다."""
    from butler_pc_core.accounting.account_dict import match_account

    cases = [
        ("임원급여 지급", "", "임원급여"),
        ("대표이사급여 지급", "", "임원급여"),
        ("직원급여 이체", "", "직원급여"),
        ("1월급여 이체", "", "직원급여"),
        ("성과급 지급", "", "상여금"),
        ("퇴직금 지급", "", "퇴직급여"),
    ]
    for desc, vendor, expected in cases:
        name, conf = match_account(desc, vendor)
        assert name == expected, (
            f"인건비 분류 실패 — '{desc}': 기대='{expected}', 실제='{name}'"
        )
        assert conf >= 0.50, f"'{desc}' 신뢰도 {conf:.0%} < 50%"


# ── 3. 영업외수익·비용 분류 ───────────────────────────────────────────────────
def test_non_operating_items_classified():
    """영업외수익(이자수익·잡이익)과 영업외비용(이자비용·잡손실)이 분류돼야 한다."""
    from butler_pc_core.accounting.account_dict import match_account

    cases = [
        ("예금이자 수령", "", "이자수익"),
        ("예금결산", "", "이자수익"),
        ("잡이익 발생", "", "잡이익"),
        ("대출이자 납부", "", "이자비용"),
        ("이자비용 지급", "", "이자비용"),
        ("잡비 처리", "", "잡손실"),
        ("기타잡비 지급", "", "잡손실"),
    ]
    for desc, vendor, expected in cases:
        name, conf = match_account(desc, vendor)
        assert name == expected, (
            f"영업외 항목 분류 실패 — '{desc}': 기대='{expected}', 실제='{name}'"
        )
        assert conf >= 0.50, f"'{desc}' 신뢰도 {conf:.0%} < 50%"


# ── 4. 벤더 키워드 80개 이상 등록 확인 ──────────────────────────────────────
def test_vendor_keywords_coverage():
    """총 vendor_patterns 수가 80개 이상이어야 한다 (다양한 거래처 매칭 커버리지)."""
    from butler_pc_core.accounting.account_dict import ACCOUNTS

    total_vendors = sum(len(a.vendor_patterns) for a in ACCOUNTS)
    assert total_vendors >= 80, (
        f"vendor_patterns 수 부족 — 기대 ≥80, 실제 {total_vendors}"
    )


# ── 5. 실데이터 패턴 분류 — IBK 주요 거래처명 ───────────────────────────────
def test_ibk_real_vendor_patterns():
    """IBK 실데이터에서 자주 등장하는 거래처명이 올바르게 분류돼야 한다."""
    from butler_pc_core.accounting.account_dict import match_account

    cases = [
        # (desc, vendor, expected_account)
        ("네이버파이낸셜", "",          "광고선전비"),    # 광고 플랫폼
        ("Amazon_AWS",    "",          "지급수수료"),    # 클라우드
        ("홍보용품",       "",          "광고선전비"),    # 홍보물
        ("정기주차비",     "",          "차량유지비"),    # 주차
        ("전기요금 납부",  "한전",      "전력비"),        # 전력
        ("법인세납부",     "국세청",    "세금과공과금"),  # 세금
        ("급여 지급",      "",          "직원급여"),      # 직원급여
        ("보험료납부",     "삼성화재",  "보험료"),        # 보험
    ]
    for desc, vendor, expected in cases:
        name, conf = match_account(desc, vendor)
        assert name == expected, (
            f"IBK 패턴 분류 실패 — 적요='{desc}' 거래처='{vendor}': "
            f"기대='{expected}', 실제='{name}' (신뢰도={conf:.0%})"
        )
        assert conf >= 0.50, (
            f"'{desc}' 신뢰도 {conf:.0%} < 50%"
        )
