from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

import butler_pc_core.accounting.assignment.authorization_replay as replay_module
from butler_pc_core.accounting.assignment.authorization_replay import (
    APPROVED_DDL_SHA256,
    AssertionReplayed,
    AuthorizationReplayRecord,
    ReplayStoreUnavailable,
    SQLiteAuthorizationReplayStore,
    build_pinned_authorization_replay_schema,
    compile_replay_row,
)
from scripts.audit.reproduce_box5_ac11_schema_constraints_v1 import (
    mutation_corpus,
)


ROOT = Path(__file__).resolve().parents[3]
DDL = (
    ROOT
    / "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql"
).read_text("utf-8")
MUTATION_MANIFEST = ROOT / "tests/fixtures/box5_ac11_schema_mutations_v1.json"
EXPECTED_SCHEMA_FINGERPRINT = (
    "1882ff1839c105c923decfb863ec9a6433cf5dda0e8255fa9d2e9b616f0d1415"
)


def _initialize(database: Path, journal_mode: str = "WAL") -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA journal_mode={journal_mode}")
        connection.executescript(DDL)


def _record(**changes: object) -> AuthorizationReplayRecord:
    values: dict[str, object] = {
        "policy_digest": "a" * 64,
        "jti": "b" * 64,
        "nonce": "A" * 22,
        "tenant_id": "tenant-round3",
        "session_id": "c" * 64,
        "action": "ASSIGNMENT_CREATE",
        "resource": "ACCOUNTING_TRANSACTION:txn-round3",
        "expires_at": 2_000_000_000,
        "consumed_at": 1_900_000_000,
    }
    values.update(changes)
    return AuthorizationReplayRecord(**values)  # type: ignore[arg-type]


_PROCESS_CODE = r"""
import pathlib, sys, time
from butler_pc_core.accounting.assignment.authorization_replay import (
    AssertionReplayed, AuthorizationReplayRecord, SQLiteAuthorizationReplayStore,
)
database = pathlib.Path(sys.argv[1])
start = pathlib.Path(sys.argv[2])
deadline = time.monotonic() + 10
while not start.exists():
    if time.monotonic() >= deadline:
        raise SystemExit(3)
    time.sleep(0.005)
record = AuthorizationReplayRecord(
    policy_digest="a" * 64, jti="b" * 64, nonce="A" * 22,
    tenant_id="tenant-round3", session_id="c" * 64,
    action="ASSIGNMENT_CREATE",
    resource="ACCOUNTING_TRANSACTION:txn-round3",
    expires_at=2_000_000_000, consumed_at=1_900_000_000,
)
try:
    SQLiteAuthorizationReplayStore.for_database(database).consume_once(record)
except AssertionReplayed:
    print("REPLAY")
else:
    print("PASS")
"""


def _spawn_consumer(database: Path, start: Path) -> subprocess.Popen[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.Popen(
        [sys.executable, "-c", _PROCESS_CODE, str(database), str(start)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_exact_replay_key_matches_normative_domain_formula() -> None:
    row = compile_replay_row(_record())
    import hashlib

    material = "\0".join(("a" * 64, "b" * 64, "A" * 22, "tenant-round3", "c" * 64))
    expected = hashlib.sha256(
        b"butler:box5:ua2:replay\0" + material.encode("utf-8")
    ).hexdigest()
    assert row[0] == expected


def test_pinned_ddl_bytes_and_reference_fingerprint_are_stable() -> None:
    contract = (
        ROOT
        / "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql"
    )
    assert hashlib.sha256(contract.read_bytes()).hexdigest() == APPROVED_DDL_SHA256
    loaded, descriptor, fingerprint = build_pinned_authorization_replay_schema()
    assert loaded == DDL
    assert fingerprint == EXPECTED_SCHEMA_FINGERPRINT
    assert descriptor["table_list"] == [
        {
            "schema": "main",
            "name": "accounting_authorization_replay_v2",
            "type": "table",
            "ncol": 10,
            "wr": 0,
            "strict": 1,
        }
    ]


def test_all_fifteen_schema_mutations_block_both_consumes_before_insert(
    tmp_path: Path,
) -> None:
    corpus = mutation_corpus(DDL)
    manifest = json.loads(MUTATION_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["expected_error_code"] == "AUTHORIZATION_REPLAY_SCHEMA_MISMATCH"
    assert {item["name"] for item in manifest["attacks"]} == set(corpus)
    assert len(corpus) == 15
    for number, (name, attack_ddl) in enumerate(sorted(corpus.items()), 1):
        database = tmp_path / f"attack-{number:02d}-{name}.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.executescript(attack_ddl)
        store = SQLiteAuthorizationReplayStore.for_database(database)
        for _ in range(2):
            with pytest.raises(ReplayStoreUnavailable) as caught:
                store.consume_once(_record())
            assert caught.value.code == "AUTHORIZATION_REPLAY_SCHEMA_MISMATCH"
        with sqlite3.connect(database) as connection:
            assert connection.execute(
                "SELECT count(*) FROM accounting_authorization_replay_v2"
            ).fetchone()[0] == 0


def test_schema_is_reverified_after_store_construction_and_after_first_consume(
    tmp_path: Path,
) -> None:
    weakened = mutation_corpus(DDL)["same_columns_no_constraints"]
    before_first = tmp_path / "before-first.sqlite3"
    _initialize(before_first)
    cached_store = SQLiteAuthorizationReplayStore.for_database(before_first)
    with sqlite3.connect(before_first) as connection:
        connection.execute("DROP TABLE accounting_authorization_replay_v2")
        connection.executescript(weakened)
    with pytest.raises(ReplayStoreUnavailable) as caught:
        cached_store.consume_once(_record())
    assert caught.value.code == "AUTHORIZATION_REPLAY_SCHEMA_MISMATCH"

    after_first = tmp_path / "after-first.sqlite3"
    _initialize(after_first)
    reused_store = SQLiteAuthorizationReplayStore.for_database(after_first)
    reused_store.consume_once(_record())
    with sqlite3.connect(after_first) as connection:
        connection.execute("DROP TABLE accounting_authorization_replay_v2")
        connection.executescript(weakened)
    with pytest.raises(ReplayStoreUnavailable) as caught:
        reused_store.consume_once(_record())
    assert caught.value.code == "AUTHORIZATION_REPLAY_SCHEMA_MISMATCH"
    with sqlite3.connect(after_first) as connection:
        assert connection.execute(
            "SELECT count(*) FROM accounting_authorization_replay_v2"
        ).fetchone()[0] == 0
    print("AC11_CONSTRUCTOR_CACHE_TOCTOU=BLOCKED ROWS=0")


@pytest.mark.parametrize(
    ("payload", "approved_digest"),
    [
        (None, APPROVED_DDL_SHA256),
        (b"\xff", APPROVED_DDL_SHA256),
        (DDL.encode("utf-8") + b"\n-- tampered\n", APPROVED_DDL_SHA256),
        (DDL.encode("utf-8"), "0" * 64),
    ],
)
def test_missing_invalid_tampered_or_wrong_digest_contract_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes | None,
    approved_digest: str,
) -> None:
    contract = tmp_path / "authorization-replay-v2.sql"
    if payload is not None:
        contract.write_bytes(payload)
    monkeypatch.setattr(replay_module, "_CONTRACT_PATH", contract)
    monkeypatch.setattr(replay_module, "APPROVED_DDL_SHA256", approved_digest)
    with pytest.raises(ReplayStoreUnavailable) as caught:
        SQLiteAuthorizationReplayStore.for_database(tmp_path / "unused.sqlite3")
    assert caught.value.code == "AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH"


def test_new_process_after_restart_blocks_same_assertion(tmp_path: Path) -> None:
    database = tmp_path / "restart.sqlite3"
    _initialize(database)
    first_start = tmp_path / "first.start"
    first = _spawn_consumer(database, first_start)
    first_start.touch()
    first_out, first_err = first.communicate(timeout=15)
    assert (first.returncode, first_out.strip(), first_err) == (0, "PASS", "")

    second_start = tmp_path / "second.start"
    second = _spawn_consumer(database, second_start)
    second_start.touch()
    second_out, second_err = second.communicate(timeout=15)
    assert (second.returncode, second_out.strip(), second_err) == (0, "REPLAY", "")
    print("AC11_RESTART_FIRST=PASS SECOND=REPLAY ROWS=1")


def test_sixteen_process_barrier_has_exactly_one_winner(tmp_path: Path) -> None:
    database = tmp_path / "multiprocess.sqlite3"
    _initialize(database)
    start = tmp_path / "start.signal"
    processes = [_spawn_consumer(database, start) for _ in range(16)]
    start.touch()
    results: list[str] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        results.append(stdout.strip())
    assert results.count("PASS") == 1
    assert results.count("REPLAY") == 15
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM accounting_authorization_replay_v2"
        ).fetchone()[0] == 1
    print("AC11_PROCESS_RACE=16 WINNERS=1 REPLAY_BLOCKED=15 ROWS=1")


@pytest.mark.parametrize("journal_mode", ["WAL", "DELETE"])
def test_thirty_two_thread_race_has_one_winner(
    tmp_path: Path, journal_mode: str
) -> None:
    database = tmp_path / f"thread-{journal_mode}.sqlite3"
    _initialize(database, journal_mode)
    store = SQLiteAuthorizationReplayStore.for_database(database)

    def consume(_: int) -> str:
        try:
            store.consume_once(_record())
            return "PASS"
        except AssertionReplayed:
            return "REPLAY"

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(consume, range(32)))
    assert results.count("PASS") == 1
    assert results.count("REPLAY") == 31
    print(
        f"AC11_THREAD_RACE_MODE={journal_mode} WORKERS=32 "
        "WINNERS=1 REPLAY_BLOCKED=31"
    )


def test_busy_read_only_corrupt_and_schema_drift_are_fail_closed(
    tmp_path: Path,
) -> None:
    busy = tmp_path / "busy.sqlite3"
    _initialize(busy)
    holder = sqlite3.connect(busy, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")

    def busy_connect() -> sqlite3.Connection:
        return sqlite3.connect(busy, timeout=0.01, isolation_level=None)

    with pytest.raises(ReplayStoreUnavailable):
        SQLiteAuthorizationReplayStore(busy_connect).consume_once(_record())
    holder.rollback()
    holder.close()

    read_only = tmp_path / "read-only.sqlite3"
    _initialize(read_only)

    def read_only_connect() -> sqlite3.Connection:
        return sqlite3.connect(read_only.as_uri() + "?mode=ro", uri=True)

    with pytest.raises(ReplayStoreUnavailable):
        SQLiteAuthorizationReplayStore(read_only_connect).consume_once(_record())

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(ReplayStoreUnavailable):
        SQLiteAuthorizationReplayStore.for_database(corrupt).consume_once(_record())

    drift = tmp_path / "drift.sqlite3"
    with sqlite3.connect(drift) as connection:
        connection.execute("CREATE TABLE accounting_authorization_replay_v2 (replay_key TEXT)")
    with pytest.raises(ReplayStoreUnavailable):
        SQLiteAuthorizationReplayStore.for_database(drift).consume_once(_record())


def test_gc_retention_boundary_and_unique_binding(tmp_path: Path) -> None:
    database = tmp_path / "retention.sqlite3"
    _initialize(database)
    store = SQLiteAuthorizationReplayStore.for_database(database)
    store.consume_once(_record(expires_at=1_000))
    assert store.purge_expired(1_000) == 0
    assert store.purge_expired(1_001) == 1

    store.consume_once(_record(jti="1" * 64, nonce="B" * 22))
    store.consume_once(_record(jti="1" * 64, nonce="C" * 22))
    store.consume_once(
        _record(jti="2" * 64, nonce="B" * 22, tenant_id="tenant-round3-b")
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM accounting_authorization_replay_v2"
        ).fetchone()[0] == 3
