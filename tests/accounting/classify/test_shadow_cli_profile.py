"""재검토팀 HOLD — GROUP_A_CLI_SHADOW_COMPANY_PROFILE_NOT_PASSED 회귀.

CLI 가 활성 profile 1개를 로드해 legacy·shadow 양쪽에 ★동일 객체로 전달하는지, 그리고 그 결과
자기계좌 거래가 CLI 경로에서도 shadow REVIEW_SELF_TRANSFER(rule 미호출)로 나오는지 검증.
제품 sidecar 경로(이미 CLOSED)는 건드리지 않는다.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from scripts import box5_shadow_compare
from butler_pc_core.company_profile.contracts import make_runtime_profile

SELF_ACCOUNT = "110-222-333"
PROFILE = make_runtime_profile(
    own_bank_holder_aliases=["테스트대표"],
    own_company_aliases=["테스트회사"],
    own_account_numbers=[SELF_ACCOUNT],
)


def _run_cli(monkeypatch, xlsx: Path, out: Path) -> None:
    class Store:
        def load_active_profile(self):
            return PROFILE

    monkeypatch.setattr(box5_shadow_compare, "CompanyProfileStore", Store)
    monkeypatch.setattr(sys, "argv", ["box5_shadow_compare.py", str(xlsx), "--out", str(out)])
    assert box5_shadow_compare.main() == 0


def test_cli_passes_same_profile_object_to_legacy_and_shadow(monkeypatch, tmp_path):
    """★ 한 번 로드한 profile 객체가 legacy·shadow 양쪽에 동일 객체로 전달된다."""
    sentinel = object()
    seen: dict[str, object] = {}

    class Store:
        def load_active_profile(self):
            return sentinel

    def fake_classify_file(path, *, company_profile):
        seen["legacy"] = company_profile
        return "df"

    def fake_shadow(df, company_profile=None):
        seen["shadow"] = company_profile
        return []

    xlsx = tmp_path / "x.xlsx"
    xlsx.write_bytes(b"dummy")  # main only checks is_file(); classify_file is stubbed
    monkeypatch.setattr(box5_shadow_compare, "CompanyProfileStore", Store)
    monkeypatch.setattr(box5_shadow_compare, "classify_file", fake_classify_file)
    monkeypatch.setattr(box5_shadow_compare, "run_shadow_over_dataframe", fake_shadow)
    monkeypatch.setattr(sys, "argv", ["box5_shadow_compare.py", str(xlsx), "--out", str(tmp_path / "o")])

    assert box5_shadow_compare.main() == 0
    assert seen["legacy"] is sentinel
    assert seen["shadow"] is sentinel          # ★ 동일 객체
    assert seen["legacy"] is seen["shadow"]


def test_cli_self_transfer_row_is_review_self_transfer_end_to_end(monkeypatch, tmp_path):
    """★ CLI 실경로: 자기계좌 거래 → shadow REVIEW_SELF_TRANSFER (제품 sidecar 와 같은 시험)."""
    xlsx = tmp_path / "bank.xlsx"
    pd.DataFrame([
        {"거래일시": "2026-03-01", "출금": 50000, "입금": 0,
         "거래내용": "계좌이체", "상대계좌번호": SELF_ACCOUNT, "상대계좌예금주명": "테스트회사"},
        {"거래일시": "2026-03-02", "출금": 9900, "입금": 0,
         "거래내용": "구독", "상대계좌번호": "999-888-777", "상대계좌예금주명": "외부업체"},
    ]).to_excel(xlsx, index=False)

    out = tmp_path / "o"
    _run_cli(monkeypatch, xlsx, out)

    records = [json.loads(line) for line in (out / "box5_shadow_compare.jsonl").read_text(encoding="utf-8").splitlines()]
    reasons = [r["shadow_reason_code"] for r in records]
    # ★ the own-account row is held as a self-transfer by the shadow via the passed profile
    assert "REVIEW_SELF_TRANSFER" in reasons
    # and no account number leaked into the comparison output
    blob = (out / "box5_shadow_compare.csv").read_text(encoding="utf-8")
    assert SELF_ACCOUNT not in blob and "110222333" not in blob
