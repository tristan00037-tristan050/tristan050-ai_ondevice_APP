"""test_income_override_consistency.py — codex P1: _INCOME_OVERRIDE ↔ account_dict 일관성 검증."""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("ACCOUNTING_NO_PEFT", "1")

from butler_pc_core.accounting.ft_classifier import ft_classify, _INCOME_OVERRIDE
from butler_pc_core.accounting.account_dict import ACCOUNT_BY_NAME


def test_rental_income_category_section_consistency():
    """임대 수입 입금 → category=임대수입, section=VI_non_op_revenue (일반 기업 K-IFRS 기준)."""
    r = ft_classify("한국빌딩 임대 수입 5,000,000원 입금", "", 5_000_000, direction="입금")
    assert r.category == "임대수입", f"category={r.category}"
    assert r.section == "VI_non_op_revenue", (
        f"section={r.section!r} — 일반 기업의 임대수입은 영업외수익(VI_non_op_revenue)이어야 함"
    )
    assert r.sign == "+"


def test_consulting_income_category_section_consistency():
    """자문 수입 입금 → category=용역매출, section=I_revenue (영업수익 일관성 확인)."""
    r = ft_classify("ABC컨설팅 자문 수입 5,000,000원 입금", "", 5_000_000, direction="입금")
    assert r.category == "용역매출", f"category={r.category}"
    assert r.section == "I_revenue", f"section={r.section}"
    assert r.sign == "+"


def test_all_income_overrides_match_account_dict():
    """_INCOME_OVERRIDE의 모든 매핑이 account_dict의 해당 계정과 section 일치."""
    mismatches: list[str] = []
    for expense_cat, (override_cat, override_sec, override_sign) in _INCOME_OVERRIDE.items():
        acc = ACCOUNT_BY_NAME.get(override_cat)
        if acc is None:
            mismatches.append(
                f"{expense_cat!r} → {override_cat!r}: account_dict에 해당 계정 없음"
            )
            continue
        if acc.section != override_sec:
            mismatches.append(
                f"{expense_cat!r} → {override_cat!r}: "
                f"override section={override_sec!r}, account_dict section={acc.section!r}"
            )
    assert not mismatches, "불일치:\n" + "\n".join(mismatches)
