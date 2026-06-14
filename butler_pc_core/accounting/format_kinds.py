from __future__ import annotations


ACCOUNTING_FORMAT_KINDS = frozenset(
    {
        "cash_flow_daily",
        "cash_flow_weekly",
        "cash_flow_monthly",
        "voucher",
        "financial_statement",
        "pnl_summary",
    }
)


def is_accounting_format_kind(value: str | None) -> bool:
    return str(value or "") in ACCOUNTING_FORMAT_KINDS
