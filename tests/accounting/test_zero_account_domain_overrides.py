from butler_pc_core.accounting.ft_classifier import ft_classify
from butler_pc_core.accounting.account_dict import ACCOUNT_BY_NAME


def test_zero_account_domain_overrides():
    cases = [
        ("특허권 무형자산 상각비 300,000원 계상", "", 300_000, "출금", "무형자산상각비", "IV_sga", "-"),
        ("USD 외화예금 환율 차익 120,000원 입금", "국민은행", 120_000, "입금", "외환차익", "VI_non_op_revenue", "+"),
        ("보유 주식 배당금 500,000원 입금", "한국예탁결제원", 500_000, "입금", "배당금수익", "VI_non_op_revenue", "+"),
        ("전기요금 220,000원 납부", "한국전력", 220_000, "출금", "수도광열비", "IV_sga", "-"),
    ]
    for desc, vendor, amount, direction, exp_cat, exp_sec, exp_sign in cases:
        r = ft_classify(desc, vendor, amount, direction)
        assert r.category == exp_cat
        assert r.section == exp_sec
        assert r.sign == exp_sign
        assert r.source == "domain_override"
        assert r.confidence >= 0.95


def test_sudogwangyeol_registered_for_downstream_summary():
    acc = ACCOUNT_BY_NAME["수도광열비"]
    assert acc.code == ACCOUNT_BY_NAME["전력비"].code
    assert acc.sign == "-"
    assert acc.section == "IV_sga"
