from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from psycopg.conninfo import conninfo_to_dict

from butler_pc_core.helper1.replay_store import (
    PostgreSQLReplayStore,
    ReplayReservation,
    ReplayReservationStore,
    ReplayStoreError,
    SQLiteReplayStore,
)

from .v51_support import NOW, b64url


def _reservation(value: int) -> ReplayReservation:
    return ReplayReservation("a" * 64, "butler/helper1/key/v51", b64url(bytes([value]) * 16), NOW + 60)


def _public_resolver(host, port, *, family, type, proto):
    assert family == 0
    assert type > 0
    assert proto > 0
    return [(2, type, proto, "", ("93.184.216.34", port))]


def test_concurrent_replay_reservation_has_exactly_one_winner(tmp_path) -> None:
    store = SQLiteReplayStore(tmp_path / "replay.sqlite3")
    item = _reservation(7)

    def reserve() -> bool:
        try:
            store.reserve_many((item,), now_epoch_s=NOW)
            return True
        except ReplayStoreError as exc:
            assert str(exc) == "EVIDENCE_REPLAY_DETECTED"
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = tuple(executor.map(lambda _: reserve(), range(16)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 15


def test_replayed_member_rolls_back_the_whole_reservation_set(tmp_path) -> None:
    store = SQLiteReplayStore(tmp_path / "replay.sqlite3")
    assert isinstance(store, ReplayReservationStore)
    first, second = _reservation(1), _reservation(2)
    store.reserve_many((first,), now_epoch_s=NOW)
    with pytest.raises(ReplayStoreError, match="EVIDENCE_REPLAY_DETECTED"):
        store.reserve_many((first, second), now_epoch_s=NOW)
    store.reserve_many((second,), now_epoch_s=NOW)


def test_same_reservation_is_rejected_by_second_process(tmp_path: Path) -> None:
    database = tmp_path / "cross-process.sqlite3"
    SQLiteReplayStore(database)
    script = """
import sys
from pathlib import Path
from butler_pc_core.helper1.replay_store import ReplayReservation, ReplayStoreError, SQLiteReplayStore
item = ReplayReservation('a' * 64, 'butler/helper1/key/v51', sys.argv[2], int(sys.argv[3]))
try:
    SQLiteReplayStore(Path(sys.argv[1])).reserve_many((item,), now_epoch_s=int(sys.argv[4]))
except ReplayStoreError as exc:
    print(str(exc))
    raise SystemExit(3)
print('RESERVED')
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
    argv = [
        sys.executable,
        "-c",
        script,
        str(database),
        _reservation(9).nonce,
        str(NOW + 60),
        str(NOW),
    ]
    first = subprocess.run(argv, env=environment, text=True, capture_output=True, check=False)
    second = subprocess.run(argv, env=environment, text=True, capture_output=True, check=False)
    assert first.returncode == 0
    assert first.stdout.strip() == "RESERVED"
    assert second.returncode == 3
    assert second.stdout.strip() == "EVIDENCE_REPLAY_DETECTED"


def test_postgresql_atomic_reservation_has_one_concurrent_winner() -> None:
    class UniqueViolation(RuntimeError):
        sqlstate = "23505"

    class Backend:
        def __init__(self) -> None:
            self.rows: set[tuple[str, str, str]] = set()
            self.lock = threading.Lock()

    backend = Backend()

    class Cursor:
        def __init__(self) -> None:
            self.pending: list[tuple[str, str, str, int]] = []

        def execute(self, statement, parameters=None):
            return None

        def executemany(self, statement, rows):
            candidates = list(rows)
            with backend.lock:
                keys = {row[:3] for row in candidates}
                if keys & backend.rows:
                    raise UniqueViolation
                backend.rows.update(keys)
            self.pending = candidates

        def close(self):
            return None

    class Connection:
        class Info:
            host = "example.invalid"
            hostaddr = "93.184.216.34"
            port = 5432

        info = Info()

        def cursor(self):
            return Cursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    def connector(dsn, *, connect_timeout):
        assert connect_timeout == 10
        return Connection()

    dsn = "postgresql://verifier@example.invalid/helper1?sslmode=verify-full"
    stores = tuple(
        PostgreSQLReplayStore(dsn, connector=connector, resolver=_public_resolver)
        for _ in range(8)
    )
    item = _reservation(11)

    def reserve(store: PostgreSQLReplayStore) -> bool:
        try:
            store.reserve_many((item,), now_epoch_s=NOW)
            return True
        except ReplayStoreError as exc:
            assert str(exc) == "EVIDENCE_REPLAY_DETECTED"
            return False

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        outcomes = tuple(executor.map(reserve, stores))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == len(stores) - 1


def test_postgresql_conninfo_rejects_routing_overrides_tls_downgrades_and_local_endpoints() -> None:
    invalid = (
        "postgresql://u@example.com/db?sslmode=verify-full&host=/tmp",
        "postgresql://u@example.com/db?sslmode=verify-full&hostaddr=127.0.0.1",
        "postgresql://u@example.com/db?sslmode=verify-full&service=local",
        "postgresql://u@example.com/db?sslmode=verify-full&passfile=/tmp/pass",
        "postgresql://u@example.com/db?sslmode=require",
        "postgresql://u@example.com/db?sslmode=verify-ca",
        "postgresql://u@localhost/db?sslmode=verify-full",
        "postgresql://u@db/db?sslmode=verify-full",
        "postgresql://u@database.local/db?sslmode=verify-full",
        "postgresql://u@127.0.0.1/db?sslmode=verify-full",
        "postgresql://u@[::1]/db?sslmode=verify-full",
        "postgresql://u@10.0.0.8/db?sslmode=verify-full",
        "postgresql://u@169.254.1.2/db?sslmode=verify-full",
        "postgresql://u@100.64.0.1/db?sslmode=verify-full",
        "postgresql://u@192.168.1.2/db?sslmode=verify-full",
    )
    for dsn in invalid:
        with pytest.raises(
            ReplayStoreError,
            match="REPLAY_STORE_(DSN_INVALID|ENDPOINT_FORBIDDEN)",
        ):
            PostgreSQLReplayStore(dsn, connector=lambda *_args, **_kwargs: None)


def test_postgresql_rejects_driver_resolved_private_endpoint() -> None:
    class Info:
        host = "replay.example.com"
        hostaddr = "127.0.0.1"
        port = 5432

    class Connection:
        info = Info()
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()

    with pytest.raises(ReplayStoreError, match="REPLAY_STORE_ENDPOINT_FORBIDDEN"):
        PostgreSQLReplayStore(
            "postgresql://u@replay.example.com/db?sslmode=verify-full",
            connector=lambda *_args, **_kwargs: connection,
            resolver=_public_resolver,
        )
    assert connection.closed is True


def test_postgresql_rejects_any_private_dns_answer_before_connecting() -> None:
    connector_calls = 0

    def resolver(host, port, *, family, type, proto):
        return [
            (2, type, proto, "", ("93.184.216.34", port)),
            (2, type, proto, "", ("10.0.0.8", port)),
        ]

    def connector(*_args, **_kwargs):
        nonlocal connector_calls
        connector_calls += 1
        raise AssertionError("connector must not run")

    with pytest.raises(ReplayStoreError, match="REPLAY_STORE_ENDPOINT_FORBIDDEN"):
        PostgreSQLReplayStore(
            "postgresql://u@replay.example.com/db?sslmode=verify-full",
            connector=connector,
            resolver=resolver,
        )
    assert connector_calls == 0


def test_postgresql_pins_every_resolved_host_port_and_address() -> None:
    captured: list[str] = []

    def resolver(host, port, *, family, type, proto):
        addresses = {
            "one.example.com": ("8.8.8.8", "1.1.1.1"),
            "two.example.com": ("2001:4860:4860::8888",),
        }[host]
        return [(2, type, proto, "", (address, port)) for address in addresses]

    class Cursor:
        def execute(self, _statement):
            return None

        def close(self):
            return None

    class Info:
        host = "two.example.com"
        hostaddr = "2001:4860:4860::8888"
        port = 6432

    class Connection:
        info = Info()

        def cursor(self):
            return Cursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    def connector(dsn, *, connect_timeout):
        captured.append(dsn)
        assert connect_timeout == 10
        return Connection()

    PostgreSQLReplayStore(
        "postgresql://u@one.example.com:5432,two.example.com:6432/db?sslmode=verify-full",
        connector=connector,
        resolver=resolver,
    )
    interpreted = conninfo_to_dict(captured[0])
    assert interpreted["host"] == "one.example.com,one.example.com,two.example.com"
    assert interpreted["hostaddr"] == "1.1.1.1,8.8.8.8,2001:4860:4860::8888"
    assert interpreted["port"] == "5432,5432,6432"
    assert interpreted["sslmode"] == "verify-full"


def test_postgresql_routing_environment_is_rejected_before_connecting(monkeypatch) -> None:
    for name in PostgreSQLReplayStore._ROUTING_ENV_KEYS:
        connector_calls = 0

        def connector(*_args, **_kwargs):
            nonlocal connector_calls
            connector_calls += 1
            raise AssertionError("connector must not run")

        with monkeypatch.context() as scoped:
            scoped.setenv(name, "attacker-controlled")
            with pytest.raises(
                ReplayStoreError,
                match="REPLAY_STORE_ROUTING_ENV_FORBIDDEN",
            ):
                PostgreSQLReplayStore(
                    "postgresql://u@replay.example.com/db?sslmode=verify-full",
                    connector=connector,
                    resolver=_public_resolver,
                )
        assert connector_calls == 0
