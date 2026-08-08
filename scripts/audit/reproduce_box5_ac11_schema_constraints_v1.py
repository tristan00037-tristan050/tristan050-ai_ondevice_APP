#!/usr/bin/env python3
"""Independent product-path AC-11 schema-constraint attack matrix."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.accounting.assignment.authorization_replay import (
    AssertionReplayed,
    AuthorizationReplayRecord,
    ReplayStoreUnavailable,
    SQLiteAuthorizationReplayStore,
)


CONTRACT = (
    ROOT
    / "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql"
)
TABLE = "accounting_authorization_replay_v2"


def replay_record() -> AuthorizationReplayRecord:
    return AuthorizationReplayRecord(
        policy_digest="a" * 64,
        jti="b" * 64,
        nonce="A" * 22,
        tenant_id="tenant-round4",
        session_id="c" * 64,
        action="ASSIGNMENT_CREATE",
        resource="ACCOUNTING_TRANSACTION:txn-round4",
        expires_at=2_000_000_000,
        consumed_at=1_900_000_000,
    )


def mutation_corpus(ddl: str) -> dict[str, str]:
    without_unique = ddl.replace(
        ",\n    UNIQUE(jti_hash, nonce_hash, tenant_id_hash, session_id_hash)",
        "",
    )
    return {
        "same_columns_no_constraints": f"""
            CREATE TABLE {TABLE} (
                replay_key TEXT, jti_hash TEXT, nonce_hash TEXT,
                tenant_id_hash TEXT, session_id_hash TEXT, action TEXT,
                resource_hash TEXT, policy_digest TEXT,
                expires_at INTEGER, consumed_at INTEGER
            );
            CREATE INDEX idx_accounting_authorization_replay_v2_expiry
            ON {TABLE}(expires_at);
        """,
        "dropped_primary_key": ddl.replace(
            "replay_key TEXT PRIMARY KEY NOT NULL",
            "replay_key TEXT NOT NULL",
        ),
        "dropped_composite_unique": without_unique,
        "non_strict": ddl.replace(") STRICT;", ");"),
        "wrong_check": ddl.replace(
            "CHECK(expires_at > 0)",
            "CHECK(expires_at >= 0)",
        ),
        "forged_unique_expiry_index": ddl.replace(
            "CREATE INDEX IF NOT EXISTS idx_accounting_authorization_replay_v2_expiry",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounting_authorization_replay_v2_expiry",
        ),
        "wrong_expiry_index_column": ddl.replace(
            f"ON {TABLE}(expires_at);",
            f"ON {TABLE}(consumed_at);",
        ),
        "partial_expiry_index": ddl.replace(
            f"ON {TABLE}(expires_at);",
            f"ON {TABLE}(expires_at) WHERE expires_at > 0;",
        ),
        "reordered_composite_unique": ddl.replace(
            "UNIQUE(jti_hash, nonce_hash, tenant_id_hash, session_id_hash)",
            "UNIQUE(nonce_hash, jti_hash, tenant_id_hash, session_id_hash)",
        ),
        "constraint_replaced_by_external_unique": without_unique
        + f"\nCREATE UNIQUE INDEX forged_replay_unique ON {TABLE}"
        "(jti_hash, nonce_hash, tenant_id_hash, session_id_hash);\n",
        "unexpected_trigger": ddl
        + f"\nCREATE TRIGGER forged_trigger AFTER INSERT ON {TABLE} "
        "BEGIN SELECT 1; END;\n",
        "extra_column": ddl.replace(
            "consumed_at INTEGER NOT NULL CHECK(consumed_at > 0),",
            "consumed_at INTEGER NOT NULL CHECK(consumed_at > 0),\n"
            "    attacker_column TEXT,",
        ),
        "changed_column_type": ddl.replace(
            "expires_at INTEGER NOT NULL",
            "expires_at TEXT NOT NULL",
        ),
        "removed_not_null": ddl.replace(
            "nonce_hash TEXT NOT NULL",
            "nonce_hash TEXT",
        ),
        "added_default": ddl.replace(
            "consumed_at INTEGER NOT NULL CHECK(consumed_at > 0)",
            "consumed_at INTEGER NOT NULL DEFAULT 1 CHECK(consumed_at > 0)",
        ),
    }


def consume_twice(database: Path) -> tuple[list[str], int]:
    store = SQLiteAuthorizationReplayStore.for_database(database)
    outcomes: list[str] = []
    for _ in range(2):
        try:
            store.consume_once(replay_record())
            outcomes.append("ACCEPTED")
        except AssertionReplayed:
            outcomes.append("REPLAY_BLOCKED")
        except ReplayStoreUnavailable as exc:
            outcomes.append("STORE_BLOCKED:" + exc.code)
    with sqlite3.connect(database) as connection:
        rows = int(connection.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0])
    return outcomes, rows


def main() -> int:
    ddl = CONTRACT.read_text(encoding="utf-8")
    corpus = mutation_corpus(ddl)
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="box5-ac11-matrix-") as temporary:
        root = Path(temporary)
        normal = root / "normal.sqlite3"
        with sqlite3.connect(normal) as connection:
            connection.executescript(ddl)
        normal_outcomes, normal_rows = consume_twice(normal)
        print("NORMAL_FIRST=" + normal_outcomes[0])
        print("NORMAL_SECOND=" + normal_outcomes[1])
        print("NORMAL_ROWS=" + str(normal_rows))
        if normal_outcomes != ["ACCEPTED", "REPLAY_BLOCKED"] or normal_rows != 1:
            failures.append("normal")

        for number, (name, attack_ddl) in enumerate(sorted(corpus.items()), 1):
            database = root / f"attack-{number:02d}.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.executescript(attack_ddl)
            outcomes, rows = consume_twice(database)
            passed = outcomes == [
                "STORE_BLOCKED:AUTHORIZATION_REPLAY_SCHEMA_MISMATCH",
                "STORE_BLOCKED:AUTHORIZATION_REPLAY_SCHEMA_MISMATCH",
            ] and rows == 0
            print(f"ATTACK_{number:02d}_NAME={name}")
            print(f"ATTACK_{number:02d}_FIRST={outcomes[0]}")
            print(f"ATTACK_{number:02d}_SECOND={outcomes[1]}")
            print(f"ATTACK_{number:02d}_ROWS={rows}")
            print(f"ATTACK_{number:02d}_FAIL_CLOSED={str(passed).upper()}")
            if not passed:
                failures.append(name)

    print("ATTACK_COUNT=" + str(len(corpus)))
    print("ATTACK_PASS_COUNT=" + str(len(corpus) - len(failures)))
    print("AC11_SCHEMA_CONSTRAINT_MATRIX_PASS=" + str(not failures).upper())
    if failures:
        print("FAILED_ATTACKS=" + ",".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
