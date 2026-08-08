"""Versioned Korean-bank row adapters for the Box5 review aggregate.

The adapters deliberately extract a counterparty identity independently from
the free-form description used for display/classification.  A caller may pin
an adapter ID after the upload parser has identified a format; otherwise the
column signature must identify exactly one adapter or ingestion fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import AssignmentError


def _text(row: Any, name: str) -> str:
    if name not in row.index:
        return ""
    value = row.get(name)
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except (TypeError, ValueError):
        return ""
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "nat", "<na>", "none"} else text


@dataclass(frozen=True, slots=True)
class BankAdapter:
    adapter_id: str
    adapter_version: str
    signature_columns: frozenset[str]
    counterparty_columns: tuple[str, ...]
    transaction_id_columns: tuple[str, ...]

    def counterparty_candidate(self, row: Any) -> str | None:
        """Return one stable candidate, never a concatenated memo/description."""

        values = []
        for column in self.counterparty_columns:
            value = _text(row, column)
            if value and value not in values:
                values.append(value)
        if not values:
            return None
        # Priority is contract data, not fuzzy scoring.  When both an account
        # identity and a holder name exist, the first (account) is authoritative.
        return values[0]

    def transaction_id_candidate(self, row: Any) -> str | None:
        for column in self.transaction_id_columns:
            value = _text(row, column)
            if value:
                return value
        return None


# IDs are stable product contract values.  Version changes require a migration;
# the order here is not a detection priority.
SUPPORTED_BANK_ADAPTERS: tuple[BankAdapter, ...] = (
    BankAdapter(
        "kr.kb.statement",
        "1.0.0",
        frozenset({"거래일시", "보낸분/받는분"}),
        ("상대계좌번호", "보낸분/받는분", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
    BankAdapter(
        "kr.ibk.statement",
        "1.0.0",
        frozenset({"거래일시", "상대계좌예금주명"}),
        ("상대계좌번호", "상대계좌예금주명", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
    BankAdapter(
        "kr.nh.statement",
        "1.0.0",
        frozenset({"거래일자", "거래시간", "거래기록사항"}),
        ("상대계좌번호", "보낸분/받는분", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
    BankAdapter(
        "kr.shinhan.statement",
        "1.0.0",
        frozenset({"거래일자", "적요", "거래점"}),
        ("상대계좌번호", "보낸분/받는분", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
    BankAdapter(
        "kr.woori.statement",
        "1.0.0",
        frozenset({"거래일시", "적요", "메모"}),
        ("상대계좌번호", "보낸분/받는분", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
    BankAdapter(
        "kr.hana.statement",
        "1.0.0",
        frozenset({"거래일시", "거래내용", "거래구분"}),
        ("상대계좌번호", "보낸분/받는분", "거래처"),
        ("거래번호", "거래고유번호"),
    ),
)

_BY_ID = {adapter.adapter_id: adapter for adapter in SUPPORTED_BANK_ADAPTERS}


def resolve_bank_adapter(columns: list[object], pinned_id: str | None = None) -> BankAdapter:
    names = frozenset(str(column).strip() for column in columns)
    if pinned_id is not None:
        adapter = _BY_ID.get(pinned_id)
        if adapter is None:
            raise AssignmentError(
                "UNSUPPORTED_BANK_ADAPTER", 422, "The bank statement adapter is unsupported."
            )
        if not adapter.signature_columns.issubset(names):
            raise AssignmentError(
                "BANK_ADAPTER_SIGNATURE_MISMATCH",
                422,
                "The bank statement columns do not match the selected adapter.",
            )
        return adapter

    matches = [
        adapter
        for adapter in SUPPORTED_BANK_ADAPTERS
        if adapter.signature_columns.issubset(names)
    ]
    if len(matches) != 1:
        raise AssignmentError(
            "AMBIGUOUS_BANK_ADAPTER" if matches else "UNSUPPORTED_BANK_ADAPTER",
            422,
            "The bank statement format could not be identified safely.",
        )
    return matches[0]
