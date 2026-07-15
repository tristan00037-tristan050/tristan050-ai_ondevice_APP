"""Run the new Stage3Classifier as a shadow over legacy-classified rows. Observe-only.

Every row is isolated: a shadow failure becomes a SHADOW_ERROR record and never propagates to the
product path. Nothing here mutates the legacy DataFrame or the product response.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from butler_pc_core.accounting.classify.models import DecisionState
from butler_pc_core.accounting.classify.pipeline import Stage3Classifier
from butler_pc_core.accounting.classify.shadow.adapter import (
    AtlinkShadowPort,
    build_canonical_transaction,
    transaction_key,
)
from butler_pc_core.accounting.classify.shadow.record import (
    Agreement,
    ShadowComparisonRecord,
    classify_agreement,
)

_UNCLASSIFIED_LABELS = {"", "미분류", "none", "None"}


def _legacy_classified(legacy_account: object) -> bool:
    return str(legacy_account if legacy_account is not None else "").strip() not in _UNCLASSIFIED_LABELS


_DATE_COL_KEYWORDS = ("거래일시", "거래일자", "거래일", "거래날짜", "일자", "날짜", "date", "일시")


def _to_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        import pandas as pd  # local; only reached from the DataFrame path

        parsed = pd.to_datetime(text, errors="coerce")
        if parsed is None or pd.isna(parsed):
            raise ValueError(f"UNPARSEABLE_DATE:{text[:16]}")
        return parsed.date()


def _detect_date_column(columns: list[str]) -> str | None:
    for col in columns:
        low = str(col).strip().lower()
        if any(kw in str(col) or kw in low for kw in _DATE_COL_KEYWORDS):
            return col
    return None


def shadow_one(row: dict[str, Any]) -> ShadowComparisonRecord:
    """Classify one row via the shadow classifier. Isolated: never raises."""
    legacy_account = row.get("legacy_account")
    legacy_status = "분류됨" if _legacy_classified(legacy_account) else "미분류"
    legacy_account_id = str(legacy_account).strip() if _legacy_classified(legacy_account) else None
    try:
        booked = _to_date(row["booked_date"])
        tx = build_canonical_transaction(
            index=int(row["index"]),
            amount_minor=int(row["amount_minor"]),
            booked_date=booked,
            value_date=_to_date(row.get("value_date", booked)),
            desc_text=row.get("desc_text", ""),
            vendor_text=row.get("vendor_text", ""),
            counterparty_text=row.get("counterparty_text", ""),
        )
        draft = Stage3Classifier().classify(tx, AtlinkShadowPort())
        shadow_classified = draft.state is DecisionState.AUTO_PROPOSE
        shadow_account_id = draft.account_id if shadow_classified else None
        return ShadowComparisonRecord(
            transaction_key=transaction_key(tx),
            legacy_status=legacy_status,
            legacy_account_id=legacy_account_id,
            shadow_status=draft.state.value,
            shadow_account_id=shadow_account_id,
            shadow_rule_id=draft.rule_id,
            shadow_rule_digest=draft.rule_digest,
            shadow_reason_code=draft.reason_code.value,
            agreement=classify_agreement(
                legacy_classified=_legacy_classified(legacy_account),
                shadow_classified=shadow_classified,
                legacy_account_id=legacy_account_id,
                shadow_account_id=shadow_account_id,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — shadow must never break the product path
        return ShadowComparisonRecord(
            transaction_key=f"row-{row.get('index', '?')}",
            legacy_status=legacy_status,
            legacy_account_id=legacy_account_id,
            shadow_status=Agreement.SHADOW_ERROR,
            shadow_account_id=None,
            shadow_rule_id=None,
            shadow_rule_digest=None,
            shadow_reason_code=None,
            agreement=Agreement.SHADOW_ERROR,
            shadow_error_code=type(exc).__name__,
        )


def run_shadow_over_rows(rows: Iterable[dict[str, Any]]) -> list[ShadowComparisonRecord]:
    return [shadow_one(row) for row in rows]


def rows_from_dataframe(df: Any) -> list[dict[str, Any]]:
    """Extract PII-free primitives from the legacy result DataFrame (best-effort)."""
    rows: list[dict[str, Any]] = []
    internal = {"분류과목", "신뢰도", "_amt", "_datetime", "_guard_reason", "_pnl_excluded"}
    columns = list(df.columns)
    date_col = _detect_date_column(columns)
    non_internal = [c for c in columns if c not in internal]
    for i, (_, r) in enumerate(df.iterrows()):
        amt = r.get("_amt")
        if amt is None:
            continue
        booked = r.get("_datetime")
        if booked is None and date_col is not None:
            booked = r.get(date_col)
        # combine non-internal cell text ONLY to compute digests downstream (never stored raw)
        desc = " ".join(str(r.get(c, "")) for c in non_internal)
        rows.append({
            "index": i,
            "amount_minor": int(round(float(amt))),
            "booked_date": booked,
            "value_date": booked,
            "desc_text": desc,
            "vendor_text": str(r.get("상대계좌예금주명", r.get("거래처", ""))),
            "counterparty_text": str(r.get("상대계좌예금주명", "")),
            "legacy_account": r.get("분류과목"),
        })
    return rows


def run_shadow_over_dataframe(df: Any) -> list[ShadowComparisonRecord]:
    """Top-level entry used by the isolated sidecar hook."""
    return run_shadow_over_rows(rows_from_dataframe(df))


def shadow_enabled() -> bool:
    """Shadow is on by default; an explicit BUTLER_BOX5_SHADOW_DISABLED=1 turns it off."""
    import os

    return os.environ.get("BUTLER_BOX5_SHADOW_DISABLED", "").strip() != "1"


def run_and_write_shadow(df: Any, out_path: str) -> int:
    """Self-contained, fully isolated sink for the sidecar hook.

    Runs the shadow over the legacy DataFrame and appends one JSONL record per row to out_path.
    Returns the number of records written, or 0 if disabled/failed. Never raises — the product
    classification path must be unaffected whatever happens here.
    """
    try:
        if not shadow_enabled():
            return 0
        records = run_shadow_over_dataframe(df)
        lines = "".join(r.to_jsonl() + "\n" for r in records)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(lines)
        return len(records)
    except Exception:  # noqa: BLE001 — observe-only; product path must never see this
        return 0
