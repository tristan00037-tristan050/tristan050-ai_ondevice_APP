from __future__ import annotations

from butler_pc_core.company_profile.contracts import make_runtime_profile
from butler_pc_core.company_profile.matcher import (
    is_account_verification,
    is_own_account,
    is_self_holder,
)
from butler_pc_core.company_profile.normalizer import normalize_holder_alias


def _profile():
    return make_runtime_profile(
        own_bank_holder_aliases=["주식회사 에이티링크", "(주)에이티링크"],
        own_company_aliases=["에이티링크"],
        own_account_numbers=["123-456789-01-029"],
    )


def test_company_name_normalization_handles_corp_markers_spaces_and_suffix():
    assert normalize_holder_alias("주식회사 에이티링크") == "에이티링크"
    assert normalize_holder_alias("㈜ 에이티 링크") == "에이티링크"
    assert normalize_holder_alias("(주)에이티링크(A") == "에이티링크"


def test_self_holder_matches_bank_holder_and_company_aliases():
    profile = _profile()

    assert is_self_holder("주식회사 에이티링크", profile) is True
    assert is_self_holder("(주)에이티링크(A", profile) is True
    assert is_self_holder("에이티링크", profile) is True
    assert is_self_holder("ABC컨설팅", profile) is False


def test_own_account_matches_normalized_digits():
    profile = _profile()

    assert is_own_account("12345678901029", profile) is True
    assert is_own_account("123-456789-01-029", profile) is True
    assert is_own_account("000-000000-00-000", profile) is False


def test_account_verification_requires_small_amount_and_verification_text():
    assert is_account_verification("계좌인증", 1) is True
    assert is_account_verification("본인 확인 입금", "1") is True
    assert is_account_verification("계좌인증", 2) is False
    assert is_account_verification("ABC컨설팅 용역 수입", 1) is False
