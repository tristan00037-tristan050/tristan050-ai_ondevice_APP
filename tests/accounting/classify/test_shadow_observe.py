"""Box5 stage-3 shadow — observe-only guarantees.

Proves: the shadow does not mutate the legacy DataFrame (byte-identical product output), the new
classifier actually runs and records a PII-free comparison, a shadow failure is isolated, the
off switch works, and nothing is auto-consumed.
"""

from __future__ import annotations

import json
import os

import pytest

pd = pytest.importorskip("pandas")

from butler_pc_core.accounting.classify.shadow.runner import (
    run_and_write_shadow,
    run_shadow_over_dataframe,
    shadow_one,
)
from butler_pc_core.accounting.classify.shadow.record import Agreement


def _df():
    return pd.DataFrame(
        [
            {"거래일시": "2026-03-01", "거래내용": "AWS 클라우드 구독", "상대계좌예금주명": "AMAZON",
             "분류과목": "지급수수료", "신뢰도": 90, "_amt": -9900.0, "_datetime": "2026-03-01"},
            {"거래일시": "2026-03-02", "거래내용": "점심 식대", "상대계좌예금주명": "김밥천국",
             "분류과목": "미분류", "신뢰도": 0, "_amt": -50000.0, "_datetime": "2026-03-02"},
            {"거래일시": "2026-03-03", "거래내용": "매출 입금", "상대계좌예금주명": "고객사",
             "분류과목": "매출", "신뢰도": 100, "_amt": 300000.0, "_datetime": "2026-03-03"},
        ]
    )


def test_shadow_does_not_mutate_dataframe():
    df = _df()
    before = df.copy(deep=True)
    run_shadow_over_dataframe(df)
    # byte-identical product output guarantee: the shadow reads df and never writes to it.
    assert df.equals(before)


def test_shadow_actually_runs_and_records(tmp_path):
    out = tmp_path / "shadow.jsonl"
    n = run_and_write_shadow(_df(), str(out))
    assert n == 3
    recs = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    # the new Stage3Classifier really ran: real states + reason codes appear
    assert all(r["shadow_status"] in {"AUTO_PROPOSE", "REVIEW_REQUIRED", "BLOCKED"} for r in recs)
    assert any(r["shadow_reason_code"] for r in recs)
    # legacy vs shadow comparison populated
    by_agree = {r["agreement"] for r in recs}
    assert by_agree & {Agreement.SHADOW_UNCLASSIFIED_LEGACY_CLASSIFIED, Agreement.BOTH_UNCLASSIFIED}


def test_shadow_records_are_pii_free(tmp_path):
    out = tmp_path / "shadow.jsonl"
    run_and_write_shadow(_df(), str(out))
    blob = out.read_text(encoding="utf-8")
    for secret in ("AWS", "AMAZON", "김밥천국", "점심", "매출 입금", "고객사"):
        assert secret not in blob


def test_shadow_never_auto_consumes(tmp_path):
    out = tmp_path / "shadow.jsonl"
    run_and_write_shadow(_df(), str(out))
    for line in out.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        assert r["auto_consumed"] is False
        assert r["journal_auto_post_allowed"] is False


def test_shadow_row_failure_is_isolated():
    # a row that cannot build a canonical tx must yield a SHADOW_ERROR record, never raise
    rec = shadow_one({"index": 0, "amount_minor": -1, "booked_date": "NOT-A-DATE", "legacy_account": "통신비"})
    assert rec.shadow_status == Agreement.SHADOW_ERROR
    assert rec.shadow_error_code is not None


def test_shadow_sink_swallows_failure(tmp_path):
    # a completely broken df must not raise out of the sink (product path protected)
    assert run_and_write_shadow(object(), str(tmp_path / "x.jsonl")) == 0


def test_shadow_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_BOX5_SHADOW_DISABLED", "1")
    out = tmp_path / "shadow.jsonl"
    assert run_and_write_shadow(_df(), str(out)) == 0
    assert not out.exists()
