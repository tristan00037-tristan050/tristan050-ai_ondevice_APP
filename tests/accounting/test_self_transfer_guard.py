from __future__ import annotations

import os

import pytest

os.environ.setdefault("ACCOUNTING_NO_PEFT", "1")

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

from butler_pc_core.company_profile.contracts import make_runtime_profile

pytestmark = pytest.mark.skipif(not _PANDAS_OK, reason="pandas 미설치")


def _profile():
    return make_runtime_profile(
        own_bank_holder_aliases=["주식회사 에이티링크", "(주)에이티링크"],
        own_company_aliases=["주식회사 에이티링크", "(주)에이티링크", "에이티링크"],
        own_account_numbers=[],
    )


def _profile_with_account():
    return make_runtime_profile(
        own_bank_holder_aliases=["주식회사 에이티링크", "(주)에이티링크"],
        own_company_aliases=["주식회사 에이티링크", "(주)에이티링크", "에이티링크"],
        own_account_numbers=["123-456789-01-029"],
    )


def _classify(rows, *, profile=None):
    from butler_pc_core.accounting.classifier import classify_df

    return classify_df(pd.DataFrame(rows).fillna(""), company_profile=profile)


def test_self_holder_income_is_guarded_before_revenue_override():
    out = _classify(
        [
            {
                "적요": "타행이체",
                "입금": "10000",
                "출금": "",
                "상대계좌예금주명": "주식회사 에이티링크",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["분류과목"] not in {"용역매출", "서비스매출"}
    assert float(row["신뢰도"]) <= 0.2
    assert row["_guard_reason"] == "SELF_HOLDER_MATCH"
    assert bool(row["_pnl_excluded"]) is True


def test_account_verification_priority_over_self_holder():
    out = _classify(
        [
            {
                "적요": "계좌인증",
                "입금": "1",
                "출금": "",
                "상대계좌예금주명": "(주)에이티링크(A",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["_guard_reason"] == "ACCOUNT_VERIFICATION"
    assert bool(row["_pnl_excluded"]) is True


def test_external_service_income_still_maps_to_service_revenue():
    out = _classify(
        [
            {
                "적요": "ABC컨설팅 용역 수입",
                "입금": "1000000",
                "출금": "",
                "상대계좌예금주명": "ABC컨설팅",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "용역매출"
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


def test_self_holder_outgoing_transfer_is_not_fee_expense():
    out = _classify(
        [
            {
                "적요": "타행이체 계좌대체",
                "입금": "",
                "출금": "12000",
                "상대계좌예금주명": "주식회사 에이티링크",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["분류과목"] != "지급수수료"
    assert row["_guard_reason"] == "SELF_HOLDER_MATCH"


def test_external_fee_payment_still_maps_to_fee_expense():
    out = _classify(
        [
            {
                "적요": "외부 거래처 수수료 지급",
                "입금": "",
                "출금": "12000",
                "상대계좌예금주명": "외부거래처",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "지급수수료"
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


def test_vendor_only_self_alias_income_is_guarded():
    out = _classify(
        [
            {
                "적요": "입금",
                "입금": "300000",
                "출금": "",
                "상대계좌예금주명": "(주)에이티링크",
            }
        ],
        profile=_profile(),
    )

    assert out.iloc[0]["분류과목"] == "미분류"
    assert out.iloc[0]["_guard_reason"] == "SELF_HOLDER_MATCH"


def test_generic_statement_account_number_does_not_guard_external_income():
    out = _classify(
        [
            {
                "적요": "ABC컨설팅 용역 수입",
                "입금": "1000000",
                "출금": "",
                "상대계좌예금주명": "ABC컨설팅",
                "계좌번호": "123-456789-01-029",
            }
        ],
        profile=_profile_with_account(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "용역매출"
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


def test_explicit_counterparty_account_number_can_guard():
    out = _classify(
        [
            {
                "적요": "타행이체",
                "입금": "50000",
                "출금": "",
                "상대계좌예금주명": "외부표기",
                "상대계좌번호": "123-456789-01-029",
            }
        ],
        profile=_profile_with_account(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["_guard_reason"] == "OWN_ACCOUNT_MATCH"
    assert bool(row["_pnl_excluded"]) is True


@pytest.mark.parametrize(
    "memo",
    [
        "사내 자금이동",
        "예금 대체입금",
        "운영자금 이체",
        "자금이동 보통예금",
        "내부이체 본사운영자금",
    ],
)
def test_strong_internal_memo_guards_without_account_or_holder(memo):
    out = _classify(
        [
            {
                "적요": memo,
                "입금": "1000000",
                "출금": "",
                "상대계좌예금주명": "외부표기",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["_guard_reason"] == "STRONG_INTERNAL_MEMO"
    assert bool(row["_pnl_excluded"]) is True


@pytest.mark.parametrize(
    "memo",
    [
        "타사 송금",
        "계좌이체 외주대금",
        "예금대체 외주대금",
        "보통예금 통신비",
    ],
)
def test_weak_transfer_memo_alone_does_not_guard(memo):
    out = _classify(
        [
            {
                "적요": memo,
                "입금": "",
                "출금": "12000",
                "상대계좌예금주명": "외부거래처",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


@pytest.mark.parametrize("memo", ["사내식당", "사내복지비", "사내교육비", "사내 식당 비용"])
def test_internal_company_substrings_without_transfer_context_do_not_guard(memo):
    out = _classify(
        [
            {
                "적요": memo,
                "입금": "",
                "출금": "12000",
                "상대계좌예금주명": "외부거래처",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


def test_standalone_replacement_word_does_not_guard_or_count_as_weak_hint():
    from butler_pc_core.company_profile.matcher import is_strong_internal_memo, is_weak_transfer_memo

    assert is_strong_internal_memo("대체") is False
    assert is_weak_transfer_memo("대체") is False
    assert is_strong_internal_memo("예금대체 외주대금") is False
    assert is_weak_transfer_memo("예금대체 외주대금") is True
    assert is_strong_internal_memo("대체입금") is True


def test_self_transfer_guard_priority_preserves_existing_order_before_strong_memo():
    rows = [
        {
            "적요": "계좌인증 내부이체",
            "입금": "1",
            "출금": "",
            "상대계좌예금주명": "(주)에이티링크",
            "상대계좌번호": "123-456789-01-029",
        },
        {
            "적요": "내부이체 본사운영자금",
            "입금": "50000",
            "출금": "",
            "상대계좌예금주명": "(주)에이티링크",
            "상대계좌번호": "123-456789-01-029",
        },
        {
            "적요": "내부이체 본사운영자금",
            "입금": "50000",
            "출금": "",
            "상대계좌예금주명": "외부표기",
            "상대계좌번호": "123-456789-01-029",
        },
        {
            "적요": "내부이체 본사운영자금",
            "입금": "50000",
            "출금": "",
            "상대계좌예금주명": "외부표기",
            "상대계좌번호": "",
        },
    ]

    out = _classify(rows, profile=_profile_with_account())

    assert list(out["_guard_reason"]) == [
        "ACCOUNT_VERIFICATION",
        "SELF_HOLDER_MATCH",
        "OWN_ACCOUNT_MATCH",
        "STRONG_INTERNAL_MEMO",
    ]


def test_single_amount_account_verification_uses_real_amount_threshold():
    out = _classify(
        [
            {
                "적요": "외부 인증 서비스 수수료 지급",
                "거래처": "외부인증서비스",
                "금액": "100000",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "지급수수료"
    assert row["_guard_reason"] == ""
    assert bool(row["_pnl_excluded"]) is False


def test_single_amount_one_won_account_verification_still_guards():
    out = _classify(
        [
            {
                "적요": "계좌인증",
                "거래처": "외부표기",
                "금액": "1",
            }
        ],
        profile=_profile(),
    )

    row = out.iloc[0]
    assert row["분류과목"] == "미분류"
    assert row["_guard_reason"] == "ACCOUNT_VERIFICATION"
    assert bool(row["_pnl_excluded"]) is True


def test_profile_none_preserves_existing_classification_path():
    rows = [
        {
            "적요": "ABC컨설팅 용역 수입",
            "입금": "1000000",
            "출금": "",
            "상대계좌예금주명": "ABC컨설팅",
        }
    ]
    without_arg = _classify(rows)
    explicit_none = _classify(rows, profile=None)

    assert explicit_none.iloc[0]["분류과목"] == without_arg.iloc[0]["분류과목"]
    assert explicit_none.iloc[0]["신뢰도"] == without_arg.iloc[0]["신뢰도"]
    assert bool(explicit_none.iloc[0]["_pnl_excluded"]) is False


def test_guarded_rows_are_excluded_from_summary_categories():
    from butler_pc_core.accounting.report import build_summary

    out = _classify(
        [
            {
                "적요": "타행이체",
                "입금": "10000",
                "출금": "",
                "상대계좌예금주명": "주식회사 에이티링크",
            },
            {
                "적요": "계좌인증",
                "입금": "1",
                "출금": "",
                "상대계좌예금주명": "(주)에이티링크(A",
            },
            {
                "적요": "ABC컨설팅 용역 수입",
                "입금": "1000000",
                "출금": "",
                "상대계좌예금주명": "ABC컨설팅",
            },
        ],
        profile=_profile(),
    )
    summary = build_summary(out)

    assert summary["total_rows"] == 3
    assert summary["classified_rows"] == 1
    assert summary["unclassified_rows"] == 2
    assert summary["guarded_rows"] == {
        "ACCOUNT_VERIFICATION": 1,
        "SELF_HOLDER_MATCH": 1,
    }
    assert set(summary["categories"]) == {"용역매출"}


def test_guarded_rows_do_not_call_ft_classify(monkeypatch):
    import butler_pc_core.accounting.classifier as classifier

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("ft_classify must not run for guarded self-transfer rows")

    monkeypatch.setattr(classifier, "ft_classify", fail_if_called)

    out = classifier.classify_df(
        pd.DataFrame(
            [
                {
                    "적요": "타행이체",
                    "입금": "10000",
                    "출금": "",
                    "상대계좌예금주명": "주식회사 에이티링크",
                }
            ]
        ).fillna(""),
        company_profile=_profile(),
    )

    assert out.iloc[0]["_guard_reason"] == "SELF_HOLDER_MATCH"


def test_strong_internal_memo_guarded_rows_do_not_call_ft_classify(monkeypatch):
    import butler_pc_core.accounting.classifier as classifier

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("ft_classify must not run for strong internal memo rows")

    monkeypatch.setattr(classifier, "ft_classify", fail_if_called)

    out = classifier.classify_df(
        pd.DataFrame(
            [
                {
                    "적요": "사내 자금이동",
                    "입금": "10000",
                    "출금": "",
                    "상대계좌예금주명": "외부표기",
                }
            ]
        ).fillna(""),
        company_profile=_profile(),
    )

    assert out.iloc[0]["_guard_reason"] == "STRONG_INTERNAL_MEMO"
