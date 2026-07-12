from __future__ import annotations

from butler_pc_core.connect_loop.scan_normalization import _apply_contextual_observed_confusables


def test_observed_confusable_applies_in_dense_numeric_window():
    mapping = {"Ο": "0"}
    assert _apply_contextual_observed_confusables("12Ο345678", mapping) == "120345678"


def test_observed_confusable_applies_with_sensitive_context_and_four_digits():
    mapping = {"Ο": "0"}
    assert _apply_contextual_observed_confusables("계좌 12Ο34", mapping) == "계좌 12034"


def test_observed_confusable_not_global_company_name_rewrite():
    mapping = {"Ο": "0"}
    assert _apply_contextual_observed_confusables("Οmega Corporation", mapping) == "Οmega Corporation"


def test_ascii_oi_l_not_mapped_by_default():
    assert _apply_contextual_observed_confusables("회사 OIL 제품 123456") == "회사 OIL 제품 123456"
