"""Append-only SQLite store for assignment, suggestion rules, and checkpoints."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import AssignmentError, ConflictDecision, EventType, RuleState, sha256_json, stable_json, utc_now
from .security import TokenService


@dataclass(frozen=True, slots=True)
class CommitResult:
    response: dict[str, Any]
    replayed: bool


class SQLiteAssignmentStore:
    """The only persistent store; raw transaction text is not representable here."""

    def __init__(self, path: Path, tokens: TokenService) -> None:
        self.path = path
        self.tokens = tokens
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assignment_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    tenant_digest TEXT NOT NULL,
                    txn_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS assignment_events_no_update
                BEFORE UPDATE ON assignment_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_EVENT'); END;
                CREATE TRIGGER IF NOT EXISTS assignment_events_no_delete
                BEFORE DELETE ON assignment_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_EVENT'); END;

                CREATE TABLE IF NOT EXISTS current_assignments (
                    tenant_digest TEXT NOT NULL,
                    txn_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    resource_version INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    PRIMARY KEY (tenant_digest, txn_id)
                );
                CREATE TABLE IF NOT EXISTS learned_rules (
                    rule_id TEXT PRIMARY KEY,
                    tenant_digest TEXT NOT NULL,
                    vendor_match_token TEXT NOT NULL,
                    adapter_family TEXT NOT NULL,
                    normalization_version TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    source_assignment_id TEXT NOT NULL,
                    source_txn_id TEXT NOT NULL,
                    registry_digest TEXT NOT NULL,
                    overlay_digest TEXT NOT NULL,
                    match_key_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deactivated_at TEXT,
                    resource_version INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_rule_per_token
                ON learned_rules(tenant_digest, vendor_match_token, adapter_family, normalization_version)
                WHERE state = 'ACTIVE_SUGGESTION';

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    tenant_digest TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    route_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    key_digest TEXT NOT NULL,
                    body_digest TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_digest, actor_id, route_id, resource_id, key_digest)
                );
                CREATE TABLE IF NOT EXISTS rule_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    tenant_digest TEXT NOT NULL,
                    txn_id TEXT NOT NULL,
                    existing_rule_id TEXT NOT NULL,
                    requested_account_id TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolution TEXT,
                    resolved_at TEXT
                );
                CREATE TABLE IF NOT EXISTS event_checkpoints (
                    tenant_digest TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL,
                    checkpoint_mac TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            rule_columns = {row[1] for row in conn.execute("PRAGMA table_info(learned_rules)")}
            if "source_txn_id" not in rule_columns:
                conn.execute("ALTER TABLE learned_rules ADD COLUMN source_txn_id TEXT NOT NULL DEFAULT ''")
            conflict_columns = {row[1] for row in conn.execute("PRAGMA table_info(rule_conflicts)")}
            if "resolution" not in conflict_columns:
                conn.execute("ALTER TABLE rule_conflicts ADD COLUMN resolution TEXT")
            if "resolved_at" not in conflict_columns:
                conn.execute("ALTER TABLE rule_conflicts ADD COLUMN resolved_at TEXT")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _begin(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise AssignmentError("STORE_BUSY", 503, "The assignment store is busy.") from exc

    @staticmethod
    def _idempotent_response(
        conn: sqlite3.Connection,
        *,
        tenant_digest: str,
        actor_id: str,
        route_id: str,
        resource_id: str,
        key_digest: str,
        body_digest: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """SELECT body_digest, response_json FROM idempotency_records
               WHERE tenant_digest=? AND actor_id=? AND route_id=? AND resource_id=? AND key_digest=?""",
            (tenant_digest, actor_id, route_id, resource_id, key_digest),
        ).fetchone()
        if row is None:
            return None
        if row["body_digest"] != body_digest:
            raise AssignmentError(
                "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY",
                409,
                "The idempotency key was already used for a different request.",
            )
        return json.loads(row["response_json"])

    def active_rule(self, tenant_digest: str, token: str, adapter_family: str, normalization: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM learned_rules WHERE tenant_digest=? AND vendor_match_token=?
                   AND adapter_family=? AND normalization_version=? AND state='ACTIVE_SUGGESTION'""",
                (tenant_digest, token, adapter_family, normalization),
            ).fetchone()
        return dict(row) if row is not None else None

    def current_assignment(self, tenant_digest: str, txn_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM current_assignments WHERE tenant_digest=? AND txn_id=?",
                (tenant_digest, txn_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def conflict(self, tenant_digest: str, conflict_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rule_conflicts WHERE tenant_digest=? AND conflict_id=?",
                (tenant_digest, conflict_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        tenant_digest: str,
        txn_id: str,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        previous = conn.execute(
            "SELECT sequence,event_hash FROM assignment_events WHERE tenant_digest=? ORDER BY sequence DESC LIMIT 1",
            (tenant_digest,),
        ).fetchone()
        if previous is not None:
            checkpoint = conn.execute(
                "SELECT sequence,event_hash,checkpoint_mac FROM event_checkpoints WHERE tenant_digest=?",
                (tenant_digest,),
            ).fetchone()
            if checkpoint is None:
                raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is missing.")
            expected_mac = self.tokens.checkpoint_mac(tenant_id, previous["event_hash"])
            if (
                checkpoint["sequence"] != previous["sequence"]
                or checkpoint["event_hash"] != previous["event_hash"]
                or not __import__("hmac").compare_digest(expected_mac, checkpoint["checkpoint_mac"])
            ):
                raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is invalid.")
        previous_hash = previous["event_hash"] if previous is not None else None
        event_id = str(payload["event_id"])
        event_payload = {**payload, "previous_event_hash": previous_hash}
        event_hash = sha256_json(event_payload)
        conn.execute(
            """INSERT INTO assignment_events
               (event_id,event_type,tenant_digest,txn_id,payload_json,previous_event_hash,event_hash,occurred_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                event_id,
                event_type.value,
                tenant_digest,
                txn_id,
                stable_json({**event_payload, "event_hash": event_hash}),
                previous_hash,
                event_hash,
                payload["occurred_at"],
            ),
        )
        sequence = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        checkpoint_mac = self.tokens.checkpoint_mac(tenant_id, event_hash)
        conn.execute(
            """INSERT INTO event_checkpoints(tenant_digest,event_hash,checkpoint_mac,sequence,updated_at)
               VALUES(?,?,?,?,?) ON CONFLICT(tenant_digest) DO UPDATE SET
               event_hash=excluded.event_hash, checkpoint_mac=excluded.checkpoint_mac,
               sequence=excluded.sequence, updated_at=excluded.updated_at""",
            (tenant_digest, event_hash, checkpoint_mac, sequence, payload["occurred_at"]),
        )
        return event_id, event_hash

    def create_assignment(
        self,
        *,
        tenant_id: str,
        tenant_digest: str,
        actor_id: str,
        txn_id: str,
        batch_id: str,
        expected_version: int,
        account_id: str,
        scope: str,
        vendor_match_token: str,
        adapter_family: str,
        normalization_version: str,
        registry_digest: str,
        overlay_digest: str,
        match_key_id: str,
        assignment_id: str,
        rule_id: str | None,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> CommitResult:
        route_id = "POST:/v1/accounting/unaccounted/{txn_id}/assign"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body_digest = sha256_json(body)
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                replay = self._idempotent_response(
                    conn,
                    tenant_digest=tenant_digest,
                    actor_id=actor_id,
                    route_id=route_id,
                    resource_id=txn_id,
                    key_digest=key_digest,
                    body_digest=body_digest,
                )
                if replay is not None:
                    conn.execute("COMMIT")
                    return CommitResult(replay, True)

                current = conn.execute(
                    "SELECT * FROM current_assignments WHERE tenant_digest=? AND txn_id=?",
                    (tenant_digest, txn_id),
                ).fetchone()
                current_version = int(current["resource_version"]) if current is not None else 1
                if current_version != expected_version:
                    raise AssignmentError(
                        "TRANSACTION_STALE",
                        412,
                        "The transaction changed before assignment.",
                        current_version=current_version,
                    )

                if rule_id is not None:
                    conflict = conn.execute(
                        """SELECT * FROM learned_rules WHERE tenant_digest=? AND vendor_match_token=?
                           AND adapter_family=? AND normalization_version=? AND state='ACTIVE_SUGGESTION'""",
                        (tenant_digest, vendor_match_token, adapter_family, normalization_version),
                    ).fetchone()
                    if conflict is not None and conflict["account_id"] != account_id:
                        conflict_id = sha256_json(
                            {"tenant": tenant_digest, "txn": txn_id, "existing": conflict["rule_id"], "body": body_digest}
                        )[:32]
                        conn.execute(
                            """INSERT OR IGNORE INTO rule_conflicts
                               (conflict_id,tenant_digest,txn_id,existing_rule_id,requested_account_id,
                                command_json,version,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                            (
                                conflict_id,
                                tenant_digest,
                                txn_id,
                                conflict["rule_id"],
                                account_id,
                                stable_json(body),
                                1,
                                "OPEN",
                                utc_now(),
                            ),
                        )
                        conn.execute("COMMIT")
                        raise AssignmentError(
                            "LEARNED_RULE_CONFLICT",
                            409,
                            "An existing suggestion rule conflicts with this account.",
                            actions=(f"RESOLVE_CONFLICT:{conflict_id}",),
                            current_version=1,
                            conflict_id=conflict_id,
                            conflict_version=1,
                            existing_account_id=str(conflict["account_id"]),
                            proposed_account_id=account_id,
                        )

                now = utc_now()
                next_version = expected_version + 1
                if current is not None:
                    supersede_event = {
                        "schema_version": "2.0",
                        "event_id": assignment_id + "_supersede",
                        "event_type": EventType.ASSIGNMENT_SUPERSEDED.value,
                        "tenant_digest": tenant_digest,
                        "batch_id": batch_id,
                        "txn_id": txn_id,
                        "assignment_id": current["assignment_id"],
                        "supersedes_assignment_id": None,
                        "rule_id": None,
                        "account_id": current["account_id"],
                        "scope": current["scope"],
                        "actor_id": actor_id,
                        "occurred_at": now,
                        "resource_version": next_version,
                        "registry_digest": registry_digest,
                        "overlay_digest": overlay_digest,
                        "match_key_id": match_key_id,
                        "normalization_version": normalization_version,
                        "reason_code": "USER_CORRECTION",
                        "checkpoint_id": None,
                    }
                    self._append_event(
                        conn,
                        tenant_id=tenant_id,
                        tenant_digest=tenant_digest,
                        txn_id=txn_id,
                        event_type=EventType.ASSIGNMENT_SUPERSEDED,
                        payload=supersede_event,
                    )

                assignment_event = {
                    "schema_version": "2.0",
                    "event_id": assignment_id,
                    "event_type": EventType.ASSIGNMENT_CREATED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": batch_id,
                    "txn_id": txn_id,
                    "assignment_id": assignment_id,
                    "supersedes_assignment_id": current["assignment_id"] if current is not None else None,
                    "rule_id": rule_id,
                    "account_id": account_id,
                    "scope": scope,
                    "actor_id": actor_id,
                    "occurred_at": now,
                    "resource_version": next_version,
                    "registry_digest": registry_digest,
                    "overlay_digest": overlay_digest,
                    "match_key_id": match_key_id,
                    "normalization_version": normalization_version,
                    "reason_code": "USER_CONFIRMED_ASSIGNMENT",
                    "checkpoint_id": None,
                }
                self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=txn_id,
                    event_type=EventType.ASSIGNMENT_CREATED,
                    payload=assignment_event,
                )
                conn.execute(
                    """INSERT INTO current_assignments
                       (tenant_digest,txn_id,assignment_id,account_id,scope,resource_version,event_id)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_digest,txn_id) DO UPDATE SET
                       assignment_id=excluded.assignment_id, account_id=excluded.account_id,
                       scope=excluded.scope, resource_version=excluded.resource_version,
                       event_id=excluded.event_id""",
                    (tenant_digest, txn_id, assignment_id, account_id, scope, next_version, assignment_id),
                )

                if rule_id is not None:
                    rule_event_id = rule_id + "_event"
                    rule_event = {
                        **assignment_event,
                        "event_id": rule_event_id,
                        "event_type": EventType.RULE_CREATED.value,
                        "assignment_id": assignment_id,
                        "rule_id": rule_id,
                        "reason_code": "USER_RULE_SUGGESTION_CREATED",
                    }
                    self._append_event(
                        conn,
                        tenant_id=tenant_id,
                        tenant_digest=tenant_digest,
                        txn_id=txn_id,
                        event_type=EventType.RULE_CREATED,
                        payload=rule_event,
                    )
                    conn.execute(
                        """INSERT INTO learned_rules
                           (rule_id,tenant_digest,vendor_match_token,adapter_family,normalization_version,
                            account_id,source_assignment_id,source_txn_id,registry_digest,overlay_digest,match_key_id,
                            state,created_at,deactivated_at,resource_version)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            rule_id,
                            tenant_digest,
                            vendor_match_token,
                            adapter_family,
                            normalization_version,
                            account_id,
                            assignment_id,
                            txn_id,
                            registry_digest,
                            overlay_digest,
                            match_key_id,
                            RuleState.ACTIVE_SUGGESTION.value,
                            now,
                            None,
                            1,
                        ),
                    )

                response = {
                    "schema_version": "2.0",
                    "assignment_id": assignment_id,
                    "txn_id": txn_id,
                    "state": "USER_ASSIGNED",
                    "account_id": account_id,
                    "scope": scope,
                    "rule_effect": "SUGGESTION_CREATED" if rule_id is not None else "NONE",
                    "rule_id": rule_id,
                    "transaction_version": next_version,
                }
                response["receipt_digest"] = sha256_json(
                    {
                        **response,
                        "tenant_digest": tenant_digest,
                        "registry_digest": registry_digest,
                        "overlay_digest": overlay_digest,
                        "idempotency_digest": key_digest,
                    }
                )
                conn.execute(
                    """INSERT INTO idempotency_records
                       (tenant_digest,actor_id,route_id,resource_id,key_digest,body_digest,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        tenant_digest,
                        actor_id,
                        route_id,
                        txn_id,
                        key_digest,
                        body_digest,
                        stable_json(response),
                        now,
                    ),
                )
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
                conn.execute("COMMIT")
                return CommitResult(response, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The assignment transaction was rolled back.") from exc

    def _verify_checkpoint_in_transaction(
        self, conn: sqlite3.Connection, tenant_id: str, tenant_digest: str
    ) -> None:
        event = conn.execute(
            "SELECT sequence,event_hash FROM assignment_events WHERE tenant_digest=? ORDER BY sequence DESC LIMIT 1",
            (tenant_digest,),
        ).fetchone()
        checkpoint = conn.execute(
            "SELECT sequence,event_hash,checkpoint_mac FROM event_checkpoints WHERE tenant_digest=?",
            (tenant_digest,),
        ).fetchone()
        if event is None or checkpoint is None:
            raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is missing.")
        expected = self.tokens.checkpoint_mac(tenant_id, event["event_hash"])
        if (
            event["sequence"] != checkpoint["sequence"]
            or event["event_hash"] != checkpoint["event_hash"]
            or not __import__("hmac").compare_digest(expected, checkpoint["checkpoint_mac"])
        ):
            raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is invalid.")

    def verify_replay(self, tenant_id: str, tenant_digest: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM assignment_events WHERE tenant_digest=? ORDER BY sequence",
                (tenant_digest,),
            ).fetchall()
            previous: str | None = None
            for row in rows:
                payload = json.loads(row["payload_json"])
                claimed_hash = payload.pop("event_hash")
                if payload.get("previous_event_hash") != previous or sha256_json(payload) != claimed_hash:
                    raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The event chain is invalid.")
                previous = claimed_hash
            if rows:
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
            return {"event_count": len(rows), "last_event_hash": previous, "passed": True}

    def list_rules(self, tenant_digest: str, state: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM learned_rules WHERE tenant_digest=?"
        params: list[Any] = [tenant_digest]
        if state is not None:
            sql += " AND state=?"
            params.append(state)
        sql += " ORDER BY created_at,rule_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def deactivate_rule(
        self,
        *,
        tenant_id: str,
        tenant_digest: str,
        actor_id: str,
        rule_id: str,
        expected_version: int,
        registry_digest: str,
        overlay_digest: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        route_id = "POST:/v1/accounting/learned-rules/{rule_id}/deactivate"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body_digest = sha256_json({"rule_id": rule_id, "expected_version": expected_version})
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                replay = self._idempotent_response(
                    conn,
                    tenant_digest=tenant_digest,
                    actor_id=actor_id,
                    route_id=route_id,
                    resource_id=rule_id,
                    key_digest=key_digest,
                    body_digest=body_digest,
                )
                if replay is not None:
                    conn.execute("COMMIT")
                    return replay
                row = conn.execute(
                    "SELECT * FROM learned_rules WHERE tenant_digest=? AND rule_id=?",
                    (tenant_digest, rule_id),
                ).fetchone()
                if row is None:
                    raise AssignmentError("RULE_NOT_FOUND", 404, "The suggestion rule was not found.")
                if int(row["resource_version"]) != expected_version:
                    raise AssignmentError(
                        "TRANSACTION_STALE", 412, "The rule changed before deactivation.", current_version=row["resource_version"]
                    )
                if row["state"] != RuleState.ACTIVE_SUGGESTION.value:
                    raise AssignmentError("RULE_ALREADY_INACTIVE", 409, "The suggestion rule is already inactive.")
                next_version = expected_version + 1
                now = utc_now()
                event_id = rule_id + f"_deactivate_{next_version}"
                payload = {
                    "schema_version": "2.0",
                    "event_id": event_id,
                    "event_type": EventType.RULE_DEACTIVATED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": None,
                    "txn_id": row["source_txn_id"],
                    "assignment_id": row["source_assignment_id"],
                    "supersedes_assignment_id": None,
                    "rule_id": rule_id,
                    "account_id": row["account_id"],
                    "scope": "SAME_VENDOR_FUTURE",
                    "actor_id": actor_id,
                    "occurred_at": now,
                    "resource_version": next_version,
                    "registry_digest": registry_digest,
                    "overlay_digest": overlay_digest,
                    "match_key_id": row["match_key_id"],
                    "normalization_version": row["normalization_version"],
                    "reason_code": "USER_RULE_DEACTIVATED",
                    "checkpoint_id": None,
                }
                self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=row["source_txn_id"],
                    event_type=EventType.RULE_DEACTIVATED,
                    payload=payload,
                )
                conn.execute(
                    "UPDATE learned_rules SET state=?,deactivated_at=?,resource_version=? WHERE rule_id=?",
                    (RuleState.INACTIVE_USER.value, now, next_version, rule_id),
                )
                response = {"rule_id": rule_id, "state": RuleState.INACTIVE_USER.value, "resource_version": next_version}
                conn.execute(
                    """INSERT INTO idempotency_records
                       (tenant_digest,actor_id,route_id,resource_id,key_digest,body_digest,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        tenant_digest,
                        actor_id,
                        route_id,
                        rule_id,
                        key_digest,
                        body_digest,
                        stable_json(response),
                        now,
                    ),
                )
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
                conn.execute("COMMIT")
                return response
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The rule transaction was rolled back.") from exc

    def resolve_conflict(
        self,
        *,
        tenant_id: str,
        tenant_digest: str,
        actor_id: str,
        conflict_id: str,
        expected_conflict_version: int,
        decision: ConflictDecision,
        txn_id: str,
        batch_id: str,
        expected_transaction_version: int,
        account_id: str,
        vendor_match_token: str,
        adapter_family: str,
        normalization_version: str,
        registry_digest: str,
        overlay_digest: str,
        match_key_id: str,
        assignment_id: str,
        replacement_rule_id: str | None,
        idempotency_key: str,
    ) -> CommitResult:
        """Resolve a recorded conflict and apply every resulting effect atomically."""
        route_id = "POST:/v1/accounting/rule-conflicts/{conflict_id}/resolve"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body = {
            "schema_version": "2.0",
            "decision": decision.value,
            "expected_conflict_version": expected_conflict_version,
        }
        body_digest = sha256_json(body)
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                replay = self._idempotent_response(
                    conn,
                    tenant_digest=tenant_digest,
                    actor_id=actor_id,
                    route_id=route_id,
                    resource_id=conflict_id,
                    key_digest=key_digest,
                    body_digest=body_digest,
                )
                if replay is not None:
                    conn.execute("COMMIT")
                    return CommitResult(replay, True)

                conflict = conn.execute(
                    "SELECT * FROM rule_conflicts WHERE tenant_digest=? AND conflict_id=?",
                    (tenant_digest, conflict_id),
                ).fetchone()
                if conflict is None:
                    raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
                if conflict["state"] != "OPEN" or int(conflict["version"]) != expected_conflict_version:
                    raise AssignmentError(
                        "CONFLICT_STALE",
                        412,
                        "The rule conflict changed before resolution.",
                        current_version=int(conflict["version"]),
                    )
                if conflict["txn_id"] != txn_id or conflict["requested_account_id"] != account_id:
                    raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict evidence no longer matches.")
                command = json.loads(conflict["command_json"])
                if command.get("scope") != "SAME_VENDOR_FUTURE" or command.get("account_id") != account_id:
                    raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict command evidence is invalid.")
                current = conn.execute(
                    "SELECT * FROM current_assignments WHERE tenant_digest=? AND txn_id=?",
                    (tenant_digest, txn_id),
                ).fetchone()
                current_version = int(current["resource_version"]) if current is not None else 1
                if current_version != expected_transaction_version:
                    raise AssignmentError(
                        "TRANSACTION_STALE",
                        412,
                        "The transaction changed before conflict resolution.",
                        current_version=current_version,
                    )
                existing = conn.execute(
                    "SELECT * FROM learned_rules WHERE tenant_digest=? AND rule_id=?",
                    (tenant_digest, conflict["existing_rule_id"]),
                ).fetchone()
                if existing is None or existing["state"] != RuleState.ACTIVE_SUGGESTION.value:
                    raise AssignmentError("CONFLICT_STALE", 412, "The existing rule is no longer active.")
                if (
                    existing["vendor_match_token"] != vendor_match_token
                    or existing["adapter_family"] != adapter_family
                    or existing["normalization_version"] != normalization_version
                ):
                    raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Conflict match evidence is invalid.")

                now = utc_now()
                next_transaction_version = expected_transaction_version + 1
                if decision is ConflictDecision.REPLACE_WITH_NEW:
                    if replacement_rule_id is None:
                        raise AssignmentError("CONFLICT_EVIDENCE_INVALID", 503, "Replacement rule identifier is missing.")
                    old_rule_version = int(existing["resource_version"]) + 1
                    deactivate_event = {
                        "schema_version": "2.0",
                        "event_id": f"{conflict_id}_deactivate",
                        "event_type": EventType.RULE_DEACTIVATED.value,
                        "tenant_digest": tenant_digest,
                        "batch_id": batch_id,
                        "txn_id": txn_id,
                        "assignment_id": existing["source_assignment_id"],
                        "supersedes_assignment_id": None,
                        "rule_id": existing["rule_id"],
                        "account_id": existing["account_id"],
                        "scope": "SAME_VENDOR_FUTURE",
                        "actor_id": actor_id,
                        "occurred_at": now,
                        "resource_version": old_rule_version,
                        "registry_digest": registry_digest,
                        "overlay_digest": overlay_digest,
                        "match_key_id": existing["match_key_id"],
                        "normalization_version": normalization_version,
                        "reason_code": "RULE_CONFLICT_REPLACED",
                        "checkpoint_id": None,
                    }
                    self._append_event(
                        conn,
                        tenant_id=tenant_id,
                        tenant_digest=tenant_digest,
                        txn_id=txn_id,
                        event_type=EventType.RULE_DEACTIVATED,
                        payload=deactivate_event,
                    )
                    conn.execute(
                        "UPDATE learned_rules SET state=?,deactivated_at=?,resource_version=? WHERE rule_id=?",
                        (RuleState.INACTIVE_USER.value, now, old_rule_version, existing["rule_id"]),
                    )

                assignment_event = {
                    "schema_version": "2.0",
                    "event_id": assignment_id,
                    "event_type": EventType.ASSIGNMENT_CREATED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": batch_id,
                    "txn_id": txn_id,
                    "assignment_id": assignment_id,
                    "supersedes_assignment_id": current["assignment_id"] if current is not None else None,
                    "rule_id": replacement_rule_id if decision is ConflictDecision.REPLACE_WITH_NEW else existing["rule_id"],
                    "account_id": account_id,
                    "scope": "SAME_VENDOR_FUTURE",
                    "actor_id": actor_id,
                    "occurred_at": now,
                    "resource_version": next_transaction_version,
                    "registry_digest": registry_digest,
                    "overlay_digest": overlay_digest,
                    "match_key_id": match_key_id,
                    "normalization_version": normalization_version,
                    "reason_code": "USER_CONFIRMED_CONFLICT_RESOLUTION",
                    "checkpoint_id": None,
                }
                self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=txn_id,
                    event_type=EventType.ASSIGNMENT_CREATED,
                    payload=assignment_event,
                )
                conn.execute(
                    """INSERT INTO current_assignments
                       (tenant_digest,txn_id,assignment_id,account_id,scope,resource_version,event_id)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_digest,txn_id) DO UPDATE SET
                       assignment_id=excluded.assignment_id,account_id=excluded.account_id,
                       scope=excluded.scope,resource_version=excluded.resource_version,event_id=excluded.event_id""",
                    (
                        tenant_digest,
                        txn_id,
                        assignment_id,
                        account_id,
                        "SAME_VENDOR_FUTURE",
                        next_transaction_version,
                        assignment_id,
                    ),
                )

                if decision is ConflictDecision.REPLACE_WITH_NEW:
                    rule_event = {
                        **assignment_event,
                        "event_id": replacement_rule_id + "_event",
                        "event_type": EventType.RULE_CREATED.value,
                        "rule_id": replacement_rule_id,
                        "reason_code": "RULE_CONFLICT_REPLACEMENT_CREATED",
                        "resource_version": 1,
                    }
                    self._append_event(
                        conn,
                        tenant_id=tenant_id,
                        tenant_digest=tenant_digest,
                        txn_id=txn_id,
                        event_type=EventType.RULE_CREATED,
                        payload=rule_event,
                    )
                    conn.execute(
                        """INSERT INTO learned_rules
                           (rule_id,tenant_digest,vendor_match_token,adapter_family,normalization_version,
                            account_id,source_assignment_id,source_txn_id,registry_digest,overlay_digest,match_key_id,
                            state,created_at,deactivated_at,resource_version)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            replacement_rule_id,
                            tenant_digest,
                            vendor_match_token,
                            adapter_family,
                            normalization_version,
                            account_id,
                            assignment_id,
                            txn_id,
                            registry_digest,
                            overlay_digest,
                            match_key_id,
                            RuleState.ACTIVE_SUGGESTION.value,
                            now,
                            None,
                            1,
                        ),
                    )

                resolved_event = {
                    **assignment_event,
                    "event_id": f"{conflict_id}_resolved",
                    "event_type": EventType.RULE_CONFLICT_RESOLVED.value,
                    "reason_code": f"CONFLICT_{decision.value}",
                }
                self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=txn_id,
                    event_type=EventType.RULE_CONFLICT_RESOLVED,
                    payload=resolved_event,
                )
                next_conflict_version = expected_conflict_version + 1
                conn.execute(
                    "UPDATE rule_conflicts SET state='RESOLVED',version=?,resolution=?,resolved_at=? WHERE conflict_id=?",
                    (next_conflict_version, decision.value, now, conflict_id),
                )
                response = {
                    "schema_version": "2.0",
                    "conflict_id": conflict_id,
                    "state": "RESOLVED",
                    "decision": decision.value,
                    "conflict_version": next_conflict_version,
                    "assignment_id": assignment_id,
                    "transaction_version": next_transaction_version,
                    "rule_effect": "SUGGESTION_REPLACED" if decision is ConflictDecision.REPLACE_WITH_NEW else "EXISTING_SUGGESTION_KEPT",
                    "rule_id": replacement_rule_id if decision is ConflictDecision.REPLACE_WITH_NEW else existing["rule_id"],
                }
                response["receipt_digest"] = sha256_json(
                    {
                        **response,
                        "tenant_digest": tenant_digest,
                        "registry_digest": registry_digest,
                        "overlay_digest": overlay_digest,
                        "idempotency_digest": key_digest,
                    }
                )
                conn.execute(
                    """INSERT INTO idempotency_records
                       (tenant_digest,actor_id,route_id,resource_id,key_digest,body_digest,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        tenant_digest,
                        actor_id,
                        route_id,
                        conflict_id,
                        key_digest,
                        body_digest,
                        stable_json(response),
                        now,
                    ),
                )
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
                conn.execute("COMMIT")
                return CommitResult(response, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("EVENT_CHECKPOINT_INVALID", 503, "The conflict transaction was rolled back.") from exc
