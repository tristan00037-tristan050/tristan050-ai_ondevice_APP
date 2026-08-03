from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")

from butler_pc_core.accounting.assignment.domain import AssignCommand, AssignmentError
from butler_pc_core.accounting.assignment.authorization_replay import (
    ReplayStoreUnavailable,
    build_pinned_authorization_replay_schema,
    verify_authorization_replay_schema,
)
from butler_pc_core.accounting.assignment.registry import RegistryEntry, RegistrySnapshot
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime
from butler_pc_core.accounting.assignment.security import MemoryKeyStore, TokenService
from butler_pc_core.accounting.assignment.stage3_store_schema_v3 import (
    ensure_stage3_v3_schema,
)
import butler_pc_core.accounting.assignment.store as store_module
from scripts.audit.reproduce_box5_ac11_schema_constraints_v1 import mutation_corpus


def _profile():
    profile_id = "stage3-product-tenant"
    return SimpleNamespace(
        status="ACTIVE",
        profile_id=profile_id,
        profile_digest=hashlib.sha256(profile_id.encode()).hexdigest(),
    )


def _session(label: str = "a"):
    return SimpleNamespace(
        actor_id=f"stage3-actor-{label}-00000001",
        session_id=f"stage3-session-{label}-000001",
        device_id=f"stage3-device-{label}-0000001",
        role="user",
    )


def _runtime(tmp_path: Path) -> AccountingReviewRuntime:
    registry = RegistrySnapshot(
        registry_digest="1" * 64,
        overlay_digest="2" * 64,
        entries=(
            RegistryEntry(
                "POSTING.A", "1001", "지급수수료", ("지급수수료",),
                "POSTING", True, None, 1,
            ),
        ),
    )
    return AccountingReviewRuntime(
        db_path=tmp_path / "stage3.sqlite3",
        key_store=MemoryKeyStore(key=b"s" * 32),
        registry=registry,
    )


@pytest.mark.parametrize(
    ("adapter_id", "row"),
    [
        ("kr.kb.statement", {"거래일시": "2026-08-01", "보낸분/받는분": "거래처", "금액": "-100"}),
        ("kr.ibk.statement", {"거래일시": "2026-08-01", "상대계좌예금주명": "거래처", "금액": "-100"}),
        ("kr.nh.statement", {"거래일자": "2026-08-01", "거래시간": "120000", "거래기록사항": "지급", "상대계좌번호": "11001", "금액": "-100"}),
        ("kr.shinhan.statement", {"거래일자": "2026-08-01", "적요": "지급", "거래점": "본점", "상대계좌번호": "11001", "금액": "-100"}),
        ("kr.woori.statement", {"거래일시": "2026-08-01", "적요": "지급", "메모": "확인", "상대계좌번호": "11001", "금액": "-100"}),
        ("kr.hana.statement", {"거래일시": "2026-08-01", "거래내용": "지급", "거래구분": "출금", "상대계좌번호": "11001", "금액": "-100"}),
    ],
)
def test_six_versioned_bank_adapters_reach_product_projection(
    tmp_path: Path, adapter_id: str, row: dict[str, str]
):
    runtime = _runtime(tmp_path)
    batch_id = "batch_" + adapter_id.replace(".", "_")
    result = runtime.ingest_dataframe(
        batch_id,
        pd.DataFrame([row]),
        _profile(),
        source_file_sha256=hashlib.sha256(adapter_id.encode()).hexdigest(),
        adapter_id=adapter_id,
    )
    assert result["adapter_id"] == adapter_id
    assert result["adapter_version"] == "1.0.0"
    assert result["total_input_rows"] == 1
    assert result["classified_rows"] + result["unaccounted_rows"] + result["quarantine_count"] + result["duplicate_linked_rows"] == 1


def test_row_conservation_and_content_duplicate_detection(tmp_path: Path):
    runtime = _runtime(tmp_path)
    normal = {"거래일시": "2026-08-01", "상대계좌예금주명": "정상 거래처", "금액": "-100"}
    frame = pd.DataFrame(
        [
            normal,
            {"거래일시": "2026-08-01", "상대계좌예금주명": "오류", "금액": "NaN"},
            {"거래일시": "2026-08-01", "상대계좌예금주명": "영원", "금액": "0"},
            {"거래일시": "invalid", "상대계좌예금주명": "날짜", "금액": "-200"},
            normal.copy(),
        ]
    )
    result = runtime.ingest_dataframe(
        "batch_row_conservation_01",
        frame,
        _profile(),
        source_file_sha256=hashlib.sha256(b"row-conservation").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    assert result["total_input_rows"] == 5
    assert result["unaccounted_rows"] == 1
    assert result["quarantine_count"] == 3
    assert result["duplicate_linked_rows"] == 1
    with sqlite3.connect(runtime.store.path) as conn:
        counts = conn.execute(
            """SELECT input_row_count,classified_count,unaccounted_count,
                      quarantined_count,duplicate_linked_count
               FROM accounting_source_batches WHERE batch_id=?""",
            ("batch_row_conservation_01",),
        ).fetchone()
    assert counts[0] == sum(counts[1:]) == 5


def test_nonce_is_bound_to_session_and_single_use(tmp_path: Path):
    runtime = _runtime(tmp_path)
    runtime.ingest_dataframe(
        "batch_nonce_security_01",
        pd.DataFrame([{"거래일시": "2026-08-01", "상대계좌예금주명": "거래처", "금액": "-100"}]),
        _profile(),
        source_file_sha256=hashlib.sha256(b"nonce-security").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    context_a = runtime.context_from_profile(_profile(), _session("a"), action="ASSIGNMENT_CREATE")
    context_b = runtime.context_from_profile(_profile(), _session("b"), action="ASSIGNMENT_CREATE")
    txn_id = runtime.unaccounted_page(context_a, "batch_nonce_security_01", cursor=None, page_size=10)["items"][0]["txn_id"]
    nonce = runtime.issue_assignment_nonce(context_a, txn_id)["user_action_nonce"]
    command = AssignCommand.from_dict(
        {
            "account_id": "POSTING.A",
            "scope": "THIS_ONLY",
            "client_action_id": str(uuid.uuid4()),
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
        }
    )
    with pytest.raises(AssignmentError, match="NONCE_INVALID"):
        runtime.assign(context_b, txn_id, command, idempotency_key=str(uuid.uuid4()), if_match_version=1)
    runtime.assign(context_a, txn_id, command, idempotency_key=str(uuid.uuid4()), if_match_version=1)
    with pytest.raises(AssignmentError, match="NONCE_REUSED"):
        runtime.assign(context_a, txn_id, command, idempotency_key=str(uuid.uuid4()), if_match_version=1)


def test_quarantine_recompile_creates_reviewable_transaction(tmp_path: Path):
    runtime = _runtime(tmp_path)
    runtime.ingest_dataframe(
        "batch_quarantine_recompile_01",
        pd.DataFrame([{"거래일시": "2026-08-01", "상대계좌예금주명": "거래처", "금액": "invalid"}]),
        _profile(),
        source_file_sha256=hashlib.sha256(b"quarantine-recompile").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    view_context = runtime.context_from_profile(_profile(), _session("q"))
    item = runtime.quarantine_page(view_context, "batch_quarantine_recompile_01")["items"][0]
    context = runtime.context_from_profile(
        _profile(), _session("q"), action="QUARANTINE_ROW_RECOMPILE"
    )
    response = runtime.recompile_quarantine(
        context,
        "batch_quarantine_recompile_01",
        item["row_id"],
        {"amount_minor": -100},
        expected_version=item["resource_version"],
        idempotency_key=str(uuid.uuid4()),
    )
    assert response["state"] == "UNACCOUNTED"
    page = runtime.unaccounted_page(
        view_context, "batch_quarantine_recompile_01", cursor=None, page_size=10
    )
    assert page["total_count"] == 1
    assert page["items"][0]["review_state"] == "REVIEW_REQUIRED"
    assert runtime.review_summary(view_context, "batch_quarantine_recompile_01")["counts"]["review_quarantine"] == 0


def test_existing_database_is_backed_up_before_stage3_migration_and_retry_is_stable(
    tmp_path: Path,
):
    database = tmp_path / "stage3.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        conn.execute("INSERT INTO legacy_marker VALUES('before-stage3')")
    first = _runtime(tmp_path)
    backup = database.with_name(database.name + ".pre-stage3-v3.backup.sqlite3")
    assert backup.is_file()
    assert backup.stat().st_mode & 0o077 == 0
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT value FROM legacy_marker").fetchone()[0] == "before-stage3"
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    backup_digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    with sqlite3.connect(first.store.path) as conn:
        assert conn.execute(
            "SELECT 1 FROM accounting_schema_migrations WHERE version=3"
        ).fetchone() == (1,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    _runtime(tmp_path)
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == backup_digest


def test_backup_failure_prevents_any_product_schema_mutation(tmp_path: Path, monkeypatch):
    database = tmp_path / "blocked.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE legacy_marker(value TEXT NOT NULL)")
        conn.execute("INSERT INTO legacy_marker VALUES('unchanged')")

    def fail_backup(_path: Path):
        raise OSError("FAULT_INJECTED_BACKUP_FAILURE")

    monkeypatch.setattr(store_module, "create_pre_migration_backup", fail_backup)
    with pytest.raises(OSError, match="FAULT_INJECTED_BACKUP_FAILURE"):
        store_module.SQLiteAssignmentStore(
            database, TokenService(MemoryKeyStore(key=b"m" * 32))
        )
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT value FROM legacy_marker").fetchone()[0] == "unchanged"
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='assignment_events'"
        ).fetchone() is None


def test_new_product_database_installs_exact_pinned_replay_schema(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _, expected_descriptor, expected_fingerprint = (
        build_pinned_authorization_replay_schema()
    )
    with sqlite3.connect(runtime.store.path) as connection:
        verify_authorization_replay_schema(
            connection,
            expected_descriptor,
            expected_fingerprint,
        )
        actual_schema_objects = [
            dict(zip(("type", "name", "tbl_name", "sql"), row, strict=True))
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM main.sqlite_schema "
                "WHERE tbl_name=? OR name=? ORDER BY type,name",
                (
                    "accounting_authorization_replay_v2",
                    "accounting_authorization_replay_v2",
                ),
            )
        ]
    assert actual_schema_objects == expected_descriptor["schema_objects"]
    assert expected_fingerprint == (
        "1882ff1839c105c923decfb863ec9a6433cf5dda0e8255fa9d2e9b616f0d1415"
    )


def test_existing_weakened_replay_schema_is_not_auto_repaired(tmp_path: Path):
    runtime = _runtime(tmp_path)
    replay_table = "accounting_authorization_replay_v2"
    pinned_ddl, _, _ = build_pinned_authorization_replay_schema()
    weakened_ddl = mutation_corpus(pinned_ddl)["same_columns_no_constraints"]
    with sqlite3.connect(runtime.store.path) as connection:
        connection.execute("DELETE FROM accounting_schema_migrations WHERE version=3")
        connection.execute(f"DROP TABLE {replay_table}")
        connection.executescript(weakened_ddl)
        weakened_sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",
            (replay_table,),
        ).fetchone()[0]
        with pytest.raises(
            ReplayStoreUnavailable,
            match="AUTHORIZATION_REPLAY_SCHEMA_MISMATCH",
        ):
            ensure_stage3_v3_schema(connection)
        retained_sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",
            (replay_table,),
        ).fetchone()[0]
        migration = connection.execute(
            "SELECT 1 FROM accounting_schema_migrations WHERE version=3"
        ).fetchone()
        rows = connection.execute(
            f"SELECT count(*) FROM {replay_table}"
        ).fetchone()[0]
    assert retained_sql == weakened_sql
    assert migration is None
    assert rows == 0
