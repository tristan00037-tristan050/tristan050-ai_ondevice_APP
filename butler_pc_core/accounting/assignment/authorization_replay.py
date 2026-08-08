"""Persistent, fail-closed replay consumption for Box5 UA2 assertions.

Production composition points this store at the canonical accounting SQLite
database.  It deliberately has no memory fallback and stores only
domain-separated digests, never an assertion or identity claim in raw form.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = frozenset(
    {
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "QUARANTINE_ROW_RECOMPILE",
        "CONFLICT_RESOLVE",
    }
)
_TABLE = "accounting_authorization_replay_v2"
_CONTRACT_PATH = Path(__file__).resolve().parent / "contracts/authorization-replay-v2.sql"
APPROVED_DDL_SHA256 = "b0e11b52b7efd3d74c41fcfb46726312ba442c2dfa7a7a04203f7424342bd729"
_REPLAY_STORE_ERROR_CODES = frozenset(
    {
        "AUTHORIZATION_REPLAY_SCHEMA_MISMATCH",
        "AUTHORIZATION_REPLAY_STORE_UNAVAILABLE",
        "AUTHORIZATION_REPLAY_INTEGRITY_FAILURE",
        "AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH",
    }
)


class AssertionReplayed(Exception):
    code = "USER_ASSERTION_REPLAYED"


class ReplayStoreUnavailable(Exception):
    def __init__(
        self, code: str = "AUTHORIZATION_REPLAY_STORE_UNAVAILABLE"
    ) -> None:
        if code not in _REPLAY_STORE_ERROR_CODES:
            raise ValueError("unstable replay-store error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AuthorizationReplayRecord:
    policy_digest: str
    jti: str
    nonce: str
    tenant_id: str
    session_id: str
    action: str
    resource: str
    expires_at: int
    consumed_at: int


class AuthorizationReplayStore(Protocol):
    def consume_once(self, record: AuthorizationReplayRecord) -> None: ...

    def purge_expired(self, cutoff: int) -> int: ...


def _digest(domain: bytes, value: str) -> str:
    if not value:
        raise ValueError("empty replay-bound value")
    return hashlib.sha256(domain + b"\0" + value.encode("utf-8")).hexdigest()


def compile_replay_row(record: AuthorizationReplayRecord) -> tuple[object, ...]:
    if (
        not _HEX64.fullmatch(record.policy_digest)
        or record.action not in _ACTIONS
        or type(record.expires_at) is not int
        or type(record.consumed_at) is not int
        or record.expires_at <= 0
        or record.consumed_at <= 0
    ):
        raise ValueError("invalid replay record")
    replay_material = "\0".join(
        (
            record.policy_digest,
            record.jti,
            record.nonce,
            record.tenant_id,
            record.session_id,
        )
    )
    return (
        _digest(b"butler:box5:ua2:replay", replay_material),
        _digest(b"butler:box5:ua2:jti", record.jti),
        _digest(b"butler:box5:ua2:nonce", record.nonce),
        _digest(b"butler:box5:ua2:tenant", record.tenant_id),
        _digest(b"butler:box5:ua2:session", record.session_id),
        record.action,
        _digest(b"butler:box5:ua2:resource", record.resource),
        record.policy_digest,
        record.expires_at,
        record.consumed_at,
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _query_dicts(
    connection: sqlite3.Connection,
    statement: str,
    parameters: tuple[object, ...],
    columns: tuple[str, ...],
) -> list[dict[str, object]]:
    rows = connection.execute(statement, parameters).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _collect_schema_descriptor(
    connection: sqlite3.Connection,
) -> dict[str, object]:
    table_list = _query_dicts(
        connection,
        "SELECT schema,name,type,ncol,wr,strict FROM pragma_table_list "
        "WHERE schema='main' AND name=? ORDER BY schema,name,type",
        (_TABLE,),
        ("schema", "name", "type", "ncol", "wr", "strict"),
    )
    table_xinfo = _query_dicts(
        connection,
        'SELECT cid,name,type,"notnull",dflt_value,pk,hidden '
        "FROM pragma_table_xinfo(?) ORDER BY cid",
        (_TABLE,),
        ("cid", "name", "type", "notnull", "dflt_value", "pk", "hidden"),
    )
    index_list = _query_dicts(
        connection,
        'SELECT name,"unique",origin,partial FROM pragma_index_list(?) '
        "ORDER BY name",
        (_TABLE,),
        ("name", "unique", "origin", "partial"),
    )
    index_xinfo: list[dict[str, object]] = []
    for index in index_list:
        name = str(index["name"])
        index_xinfo.append(
            {
                "index_name": name,
                "columns": _query_dicts(
                    connection,
                    "SELECT seqno,cid,name,desc,coll,key "
                    "FROM pragma_index_xinfo(?) ORDER BY seqno",
                    (name,),
                    ("seqno", "cid", "name", "desc", "coll", "key"),
                ),
            }
        )
    schema_objects = _query_dicts(
        connection,
        "SELECT type,name,tbl_name,sql FROM main.sqlite_schema "
        "WHERE tbl_name=? OR name=? ORDER BY type,name",
        (_TABLE, _TABLE),
        ("type", "name", "tbl_name", "sql"),
    )
    return {
        "table_list": table_list,
        "table_xinfo": table_xinfo,
        "index_list": index_list,
        "index_xinfo": index_xinfo,
        "schema_objects": schema_objects,
    }


def _schema_fingerprint(descriptor: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json(descriptor)).hexdigest()


def load_pinned_authorization_replay_ddl() -> str:
    """Load the repository-owned DDL only after its raw bytes are pinned."""

    try:
        raw = _CONTRACT_PATH.read_bytes()
    except OSError as exc:
        raise ReplayStoreUnavailable(
            "AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH"
        ) from exc
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, APPROVED_DDL_SHA256):
        raise ReplayStoreUnavailable("AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ReplayStoreUnavailable(
            "AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH"
        ) from exc


def _build_expected_schema_descriptor(
    ddl: str,
) -> tuple[dict[str, object], str]:
    reference = sqlite3.connect(":memory:", isolation_level=None)
    try:
        reference.execute("PRAGMA trusted_schema=OFF")
        reference.execute("PRAGMA writable_schema=OFF")
        reference.execute("PRAGMA foreign_keys=ON")
        reference.executescript(ddl)
        descriptor = _collect_schema_descriptor(reference)
        return descriptor, _schema_fingerprint(descriptor)
    except sqlite3.DatabaseError as exc:
        raise ReplayStoreUnavailable(
            "AUTHORIZATION_REPLAY_DDL_CONTRACT_MISMATCH"
        ) from exc
    finally:
        reference.close()


def build_pinned_authorization_replay_schema(
) -> tuple[str, dict[str, object], str]:
    """Return only the repository-pinned DDL and its reference descriptor."""

    ddl = load_pinned_authorization_replay_ddl()
    descriptor, fingerprint = _build_expected_schema_descriptor(ddl)
    return ddl, descriptor, fingerprint


def verify_authorization_replay_schema(
    connection: sqlite3.Connection,
    expected_descriptor: dict[str, object],
    expected_fingerprint: str,
) -> None:
    """Compare a product DB observation with the pinned reference schema."""

    actual = _collect_schema_descriptor(connection)
    if (
        not hmac.compare_digest(
            _schema_fingerprint(actual), expected_fingerprint
        )
        or actual != expected_descriptor
    ):
        raise ReplayStoreUnavailable("AUTHORIZATION_REPLAY_SCHEMA_MISMATCH")


_INSERT = """
INSERT INTO accounting_authorization_replay_v2 (
  replay_key, jti_hash, nonce_hash, tenant_id_hash, session_id_hash,
  action, resource_hash, policy_digest, expires_at, consumed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteAuthorizationReplayStore:
    """Atomic UA2 replay consumer backed by one canonical SQLite file."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        (
            _ddl,
            self._expected_descriptor,
            self._expected_fingerprint,
        ) = build_pinned_authorization_replay_schema()

    @classmethod
    def for_database(cls, database: Path) -> "SQLiteAuthorizationReplayStore":
        fixed = database.resolve()

        def connect() -> sqlite3.Connection:
            connection = sqlite3.connect(
                str(fixed), timeout=5.0, isolation_level=None
            )
            return connection

        return cls(connect)

    def _verify_schema_in_transaction(
        self, connection: sqlite3.Connection
    ) -> None:
        verify_authorization_replay_schema(
            connection,
            self._expected_descriptor,
            self._expected_fingerprint,
        )

    @staticmethod
    def _rollback(connection: sqlite3.Connection | None) -> None:
        if connection is None:
            return
        try:
            connection.rollback()
        except sqlite3.DatabaseError:
            pass

    @staticmethod
    def _prepare_connection(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA writable_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

    def consume_once(self, record: AuthorizationReplayRecord) -> None:
        try:
            row = compile_replay_row(record)
        except (TypeError, UnicodeError, ValueError) as exc:
            raise ReplayStoreUnavailable() from exc
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            self._prepare_connection(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._verify_schema_in_transaction(connection)
            connection.execute(_INSERT, row)
            connection.commit()
        except ReplayStoreUnavailable:
            self._rollback(connection)
            raise
        except sqlite3.IntegrityError as exc:
            self._rollback(connection)
            if getattr(exc, "sqlite_errorcode", None) in {
                sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
                sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            }:
                raise AssertionReplayed() from exc
            raise ReplayStoreUnavailable(
                "AUTHORIZATION_REPLAY_INTEGRITY_FAILURE"
            ) from exc
        except (sqlite3.DatabaseError, OSError) as exc:
            self._rollback(connection)
            raise ReplayStoreUnavailable() from exc
        finally:
            if connection is not None:
                connection.close()

    def purge_expired(self, cutoff: int) -> int:
        if type(cutoff) is not int or cutoff <= 0:
            raise ReplayStoreUnavailable()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            self._prepare_connection(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._verify_schema_in_transaction(connection)
            cursor = connection.execute(
                "DELETE FROM accounting_authorization_replay_v2 WHERE expires_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            connection.commit()
            return deleted
        except ReplayStoreUnavailable:
            self._rollback(connection)
            raise
        except sqlite3.IntegrityError as exc:
            self._rollback(connection)
            raise ReplayStoreUnavailable(
                "AUTHORIZATION_REPLAY_INTEGRITY_FAILURE"
            ) from exc
        except (sqlite3.DatabaseError, OSError) as exc:
            self._rollback(connection)
            raise ReplayStoreUnavailable() from exc
        finally:
            if connection is not None:
                connection.close()
