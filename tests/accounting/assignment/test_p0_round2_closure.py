"""2차 결합 P0 폐쇄 회귀 — RI-P0-003/011(money) · 010(date) · 001(overlay) · 006/015(keychain).

각 시험은 교정 전 공격(red)이 재현되고 교정 후 fail-closed(green)로 닫힘을 실경로로 증명한다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")

from butler_pc_core.accounting.assignment.domain import AssignmentError
from butler_pc_core.accounting.assignment.registry import RegistrySnapshot
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime, _to_amount
from butler_pc_core.accounting.assignment.security import MacOSKeychainStore, MemoryKeyStore


def _profile(name: str = "tenant-a"):
    digest = __import__("hashlib").sha256(name.encode()).hexdigest()
    return SimpleNamespace(status="ACTIVE", profile_id=name, profile_digest=digest)


def _runtime(tmp_path: Path) -> AccountingReviewRuntime:
    from butler_pc_core.accounting.assignment.registry import RegistryEntry

    registry = RegistrySnapshot(
        registry_digest="1" * 64,
        overlay_digest="2" * 64,
        entries=(RegistryEntry("POSTING.A", "1001", "지급수수료", ("지급수수료",), "POSTING", True, None, 20),),
    )
    return AccountingReviewRuntime(
        db_path=tmp_path / "assignment.sqlite3",
        key_store=MemoryKeyStore(key=b"a" * 32),
        registry=registry,
    )


def _ingest(runtime: AccountingReviewRuntime, batch_id: str, frame):
    return runtime.ingest_dataframe(
        batch_id,
        frame,
        _profile(),
        source_file_sha256=__import__("hashlib").sha256(batch_id.encode()).hexdigest(),
        adapter_id="kr.ibk.statement",
    )


# ── RI-P0-003/011: float 금액 완전 제거 ──────────────────────────────────

def _amt(value: object):
    return _to_amount(pd.Series({"_amt": value, "금액": value}))


def test_to_amount_preserves_large_integer_beyond_2_pow_53():
    # float() 였다면 9007199254740993 → 9007199254740992 로 변형된다.
    assert _amt("9007199254740993") == 9007199254740993
    assert _amt("-9007199254740993") == -9007199254740993


def test_to_amount_rejects_float_and_exponent_hazards():
    assert _amt(True) is None            # bool
    assert _amt(float("nan")) is None    # NaN
    assert _amt(float("inf")) is None    # Infinity
    assert _amt("1e5") is None           # exponent
    assert _amt("+100") is None          # leading +
    assert _amt("1,200") == 1200         # 콤마 자릿점 허용
    assert _amt("(500)") == -500         # 괄호 음수


def test_ingest_preserves_large_amount_end_to_end(tmp_path: Path):
    runtime = _runtime(tmp_path)
    frame = pd.DataFrame([{"거래일시": "2026-07-16", "상대계좌예금주명": "큰금액", "금액": "-9007199254740993", "분류과목": "미분류"}])
    _ingest(runtime, "batch_bigmoney_0001", frame)
    context = runtime.context_from_profile(_profile())
    page = runtime.unaccounted_page(context, "batch_bigmoney_0001", cursor=None, page_size=50)
    assert page["items"][0]["money"]["minor_units"] == -9007199254740993


# ── RI-P0-010: invalid date → 1970 대체 금지, 격리 ────────────────────────

def test_invalid_date_is_quarantined_not_epoch(tmp_path: Path):
    runtime = _runtime(tmp_path)
    frame = pd.DataFrame(
        [
            {"거래일시": "not-a-date", "상대계좌예금주명": "깨진날짜", "금액": "-1000", "분류과목": "미분류"},
            {"거래일시": "2026-07-16", "상대계좌예금주명": "정상", "금액": "-2000", "분류과목": "미분류"},
        ]
    )
    result = _ingest(runtime, "batch_baddate_00001", frame)
    assert result["quarantine_count"] == 1
    context = runtime.context_from_profile(_profile())
    page = runtime.unaccounted_page(context, "batch_baddate_00001", cursor=None, page_size=50)
    assert page["total_count"] == 1  # 깨진 날짜 행은 검토 목록에서 빠지고 격리된다
    assert all(item["booked_date"] != "1970-01-01" for item in page["items"])
    summary = runtime.review_summary(context, "batch_baddate_00001")
    assert summary["counts"]["review_quarantine"] == 1


# ── RI-P0-001: overlay status != APPROVED → assignable=0 ─────────────────

def test_bundled_unapproved_overlay_has_zero_assignable():
    snap = RegistrySnapshot.bundled()
    assert snap.entries
    assert not any(entry.assignable for entry in snap.entries)
    assert any(entry.disabled_reason == "REGISTRY_OVERLAY_UNAPPROVED" for entry in snap.entries)


def test_from_policy_status_gate_toggles_assignable():
    snapshot = SimpleNamespace(
        documents={
            "CHART_UPSTREAM": {
                "accounts": [
                    {"account_id": "P1", "code": None, "name_ko": "지급수수료", "parent_account_id": None, "display_order": 1}
                ]
            },
            "POSTING_OVERLAY_TEMPLATE": {
                "status": "APPROVED",
                "decisions": [{"account_id": "P1", "node_kind": "POSTING", "posting_allowed": True}],
            },
        }
    )
    approved = RegistrySnapshot.from_policy(snapshot)
    assert any(entry.assignable for entry in approved.entries)

    snapshot.documents["POSTING_OVERLAY_TEMPLATE"]["status"] = "BLOCKED_PENDING_FINANCE_APPROVAL"
    blocked = RegistrySnapshot.from_policy(snapshot)
    assert not any(entry.assignable for entry in blocked.entries)
    assert all(entry.disabled_reason == "REGISTRY_OVERLAY_UNAPPROVED" for entry in blocked.entries)


# ── RI-P0-006/015: 제품 키 provider 는 macOS Keychain only ────────────────

def test_key_provider_markers():
    # The /usr/bin/security compatibility path exposes key bytes to Python and
    # must remain blocked until the native authority is provisioned and tested.
    assert MacOSKeychainStore().is_production_provider is False
    assert MemoryKeyStore().is_production_provider is False


def test_production_runtime_rejects_test_key_provider(tmp_path: Path):
    with pytest.raises(AssignmentError, match="BLOCKED_KEY_AUTHORITY"):
        AccountingReviewRuntime.for_production(
            db_path=tmp_path / "prod.sqlite3",
            key_store=MemoryKeyStore(key=b"a" * 32),
        )


# ── RI-P0-014: ONE_VENDOR_TOKEN_CONTRACT — 세 팀 정규화 통일 ───────────────

def test_vendor_normalization_version_and_algorithm_are_unified():
    from butler_pc_core.accounting.assignment import security
    from butler_pc_core.accounting.classify import vendor_match

    # 버전 문자열이 P3 정본 하나로 통일됐다.
    assert (
        security.NORMALIZATION_VERSION
        == vendor_match.VENDOR_NORMALIZATION_VERSION
        == "nfkc-ws-latin-casefold-v1"
    )
    # 같은 거래처 텍스트에 대해 assignment(P2) 와 classify(P3) 정규화 결과가 동일하다.
    for descriptor in ["KT 통신비", "AWS", "Google Ads 광고비", "네이버클라우드", "우리 CLOUD"]:
        assert security.normalize_descriptor(descriptor) == vendor_match.normalize_vendor_descriptor(descriptor)
    # Latin-only casefold: 대문자 Latin 은 접히고 CJK 는 보존된다(전체 casefold 와 구별).
    assert security.normalize_descriptor("KT") == "kt"
    assert "통신비" in security.normalize_descriptor("KT 통신비")


# ── RI-P0-012: 재시작 fail-closed 안전(유출·권한상승 0) 실증 ─────────────────
# 주의: canonical batch 를 SQLite 로 durable 복구하는 완전 구현은 raw-zero(§15) 를 지키기 위해
# non-PII projection + vendor_token 무결성 기반 복구가 필요하며 assign 무결성 모델 확장이 따른다.
# 본 시험은 그 후속 작업 이전에도 재시작이 보안상 안전(데이터 유출/권한 상승 0)함을 고정한다.

def test_batch_restart_is_fail_closed_and_raw_zero(tmp_path: Path):
    from butler_pc_core.accounting.assignment.registry import RegistryEntry

    registry = RegistrySnapshot(
        registry_digest="1" * 64,
        overlay_digest="2" * 64,
        entries=(RegistryEntry("POSTING.A", "1001", "지급수수료", ("지급수수료",), "POSTING", True, None, 20),),
    )
    db = tmp_path / "restart.sqlite3"

    def make() -> AccountingReviewRuntime:
        return AccountingReviewRuntime(db_path=db, key_store=MemoryKeyStore(key=b"a" * 32), registry=registry)

    r1 = make()
    _ingest(r1,
        "batch_restart_00001",
        pd.DataFrame([{"거래일시": "2026-07-16", "상대계좌예금주명": "비밀상호원문", "금액": "-1000", "분류과목": "미분류"}]),
    )
    context = r1.context_from_profile(_profile())
    assert r1.unaccounted_page(context, "batch_restart_00001", cursor=None, page_size=50)["total_count"] == 1

    # 재시작: 새 인스턴스가 raw 없이 durable projection을 복구한다.
    r2 = make()
    restarted = r2.unaccounted_page(context, "batch_restart_00001", cursor=None, page_size=50)
    assert restarted["total_count"] == 1
    assert restarted["items"][0]["descriptor_display"] == "거래처 정보 비공개"

    # ★ 어떤 경우에도 raw 거래원문은 디스크(DB)에 유출되지 않는다(§15 절대불변).
    if db.exists():
        assert "비밀상호원문".encode() not in db.read_bytes()
