"""Append-only SQLite store for assignment, suggestion rules, and checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain import (
    AssignmentError,
    ConflictDecision,
    EventType,
    RuleState,
    TenantContext,
    sha256_json,
    stable_json,
    utc_now,
)
from .security import TokenService
from .a4_store_schema_v32 import ensure_a4_v32_schema
from .stage3_store_schema_v3 import create_pre_migration_backup, ensure_stage3_v3_schema


A4_VERIFIER_AUTHORITY_TRUST_PATH = (
    Path(__file__).resolve().parents[1]
    / "classify"
    / "contracts"
    / "a4_v31"
    / "verifier_authority_trust.production.json"
)
A4_ALLOW_TEST_VERIFIER_AUTHORITY = False
_PRIVILEGED_AUTHORIZATION_ACTIONS = frozenset(
    {
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "QUARANTINE_ROW_RECOMPILE",
        "CONFLICT_RESOLVE",
    }
)


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
        self._a4_schema_ready = False
        self._a4_authority_trust_path = A4_VERIFIER_AUTHORITY_TRUST_PATH
        self._a4_allow_test_authority = A4_ALLOW_TEST_VERIFIER_AUTHORITY
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        create_pre_migration_backup(path)
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

                CREATE TABLE IF NOT EXISTS account_identity_continuity (
                    tenant_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    lookup_key_id TEXT NOT NULL,
                    lookup_token TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    PRIMARY KEY (tenant_id, account_id, lookup_key_id),
                    UNIQUE (tenant_id, lookup_key_id, lookup_token)
                );
                CREATE TABLE IF NOT EXISTS recon_run (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    nonce_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('NEW','COMPILED','GRAPH_BUILT','CLASSIFIED','PREPARED','COMMITTED',
                         'EXPORT_PENDING','EXPORTED','VERIFIED','BLOCKED')),
                    code_tree_oid TEXT NOT NULL,
                    input_closure_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS recon_transaction (
                    tenant_id TEXT NOT NULL,
                    txn_uid TEXT NOT NULL,
                    source_row_digest TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    resolved_counterparty_account_id TEXT,
                    counterparty_resolution TEXT NOT NULL CHECK(counterparty_resolution IN
                        ('EXACT_VERIFIED','MASKED','MISSING','UNRESOLVED','CONFLICT')),
                    direction TEXT NOT NULL CHECK(direction IN ('INFLOW','OUTFLOW')),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL CHECK(length(currency) = 3),
                    booked_at_utc TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    value_date TEXT,
                    duplicate_of_reference_token TEXT,
                    reversal_of_reference_token TEXT,
                    PRIMARY KEY (tenant_id, txn_uid),
                    UNIQUE (tenant_id, source_row_digest)
                    ,CHECK((counterparty_resolution='EXACT_VERIFIED') =
                           (resolved_counterparty_account_id IS NOT NULL))
                );
                CREATE TABLE IF NOT EXISTS recon_run_transaction (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    txn_uid TEXT NOT NULL,
                    artifact_token TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, txn_uid),
                    UNIQUE (tenant_id, run_id, artifact_token),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id),
                    FOREIGN KEY (tenant_id, txn_uid) REFERENCES recon_transaction(tenant_id, txn_uid)
                );
                CREATE TABLE IF NOT EXISTS recon_edge (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    left_txn_uid TEXT NOT NULL,
                    right_txn_uid TEXT NOT NULL,
                    fee_txn_uid TEXT,
                    fee_mode TEXT NOT NULL CHECK(fee_mode IN ('NO_FEE','EMBEDDED_DEBIT','SEPARATE_FEE_ROW')),
                    fee_minor INTEGER NOT NULL CHECK(fee_minor >= 0),
                    eligibility_basis TEXT NOT NULL CHECK(eligibility_basis IN
                        ('RECIPROCAL_ACCOUNT','TRACE_AND_ACCOUNT')),
                    binding_digest TEXT NOT NULL,
                    cost_tuple_jcs BLOB NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, edge_id),
                    CHECK(left_txn_uid < right_txn_uid),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS recon_classification (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    classification_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('FORCED','AMBIGUOUS','UNMATCHED','BLOCKED')),
                    affects_reporting INTEGER NOT NULL CHECK(affects_reporting = 0),
                    payload_digest TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, classification_id),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS recon_policy_receipt (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    signer_key_id TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, policy_id),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS recon_review (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK(decision IN ('ACCEPT','REJECT','DEFER')),
                    actor_id TEXT NOT NULL,
                    idempotency_digest TEXT NOT NULL,
                    affects_reporting INTEGER NOT NULL CHECK(affects_reporting = 0),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, review_id),
                    UNIQUE (tenant_id, run_id, idempotency_digest),
                    FOREIGN KEY (tenant_id, run_id, edge_id) REFERENCES recon_edge(tenant_id, run_id, edge_id)
                );
                CREATE TABLE IF NOT EXISTS recon_evidence_payload (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    payload_jcs BLOB NOT NULL,
                    sha256 TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id, path),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS recon_outbox (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    expected_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('PENDING','EXPORTED','BLOCKED')),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
                    PRIMARY KEY (tenant_id, run_id, seq),
                    UNIQUE (tenant_id, run_id, path),
                    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
                );
                CREATE TRIGGER IF NOT EXISTS account_identity_continuity_no_delete
                BEFORE DELETE ON account_identity_continuity BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_transaction_no_update
                BEFORE UPDATE ON recon_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_transaction_no_delete
                BEFORE DELETE ON recon_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_run_transaction_no_update
                BEFORE UPDATE ON recon_run_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_run_transaction_no_delete
                BEFORE DELETE ON recon_run_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_edge_no_update
                BEFORE UPDATE ON recon_edge BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_edge_no_delete
                BEFORE DELETE ON recon_edge BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_classification_no_update
                BEFORE UPDATE ON recon_classification BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_classification_no_delete
                BEFORE DELETE ON recon_classification BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_policy_receipt_no_update
                BEFORE UPDATE ON recon_policy_receipt BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_policy_receipt_no_delete
                BEFORE DELETE ON recon_policy_receipt BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_review_no_update
                BEFORE UPDATE ON recon_review BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_review_no_delete
                BEFORE DELETE ON recon_review BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_evidence_payload_no_update
                BEFORE UPDATE ON recon_evidence_payload BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                CREATE TRIGGER IF NOT EXISTS recon_evidence_payload_no_delete
                BEFORE DELETE ON recon_evidence_payload BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
                """
            )
            rule_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(learned_rules)")
            }
            if "source_txn_id" not in rule_columns:
                conn.execute(
                    "ALTER TABLE learned_rules ADD COLUMN source_txn_id TEXT NOT NULL DEFAULT ''"
                )
            conflict_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(rule_conflicts)")
            }
            if "resolution" not in conflict_columns:
                conn.execute("ALTER TABLE rule_conflicts ADD COLUMN resolution TEXT")
            if "resolved_at" not in conflict_columns:
                conn.execute("ALTER TABLE rule_conflicts ADD COLUMN resolved_at TEXT")
            transaction_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(recon_transaction)")
            }
            if "resolved_counterparty_account_id" not in transaction_columns:
                conn.execute(
                    "ALTER TABLE recon_transaction ADD COLUMN resolved_counterparty_account_id TEXT"
                )
            if "counterparty_resolution" not in transaction_columns:
                conn.execute(
                    "ALTER TABLE recon_transaction ADD COLUMN counterparty_resolution TEXT"
                )
            edge_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(recon_edge)")
            }
            if "eligibility_basis" not in edge_columns:
                conn.execute("ALTER TABLE recon_edge ADD COLUMN eligibility_basis TEXT")
            if "binding_digest" not in edge_columns:
                conn.execute("ALTER TABLE recon_edge ADD COLUMN binding_digest TEXT")
            self._a4_schema_ready = ensure_a4_v32_schema(conn)
            ensure_stage3_v3_schema(conn)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _begin(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise AssignmentError(
                "STORE_BUSY", 503, "The assignment store is busy."
            ) from exc

    def _require_a4_schema(self) -> None:
        if not self._a4_schema_ready:
            raise AssignmentError(
                "BLOCK_SCHEMA_MIGRATION_REQUIRED",
                503,
                "A4 requires an explicit migration of existing reconciliation evidence.",
            )

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
                "IDEMPOTENCY_KEY_REUSE_MISMATCH",
                409,
                "The idempotency key was already used for a different request.",
            )
        return json.loads(row["response_json"])

    def persist_review_batch(
        self,
        *,
        batch: dict[str, Any],
        rows: list[dict[str, Any]],
        receipts: list[dict[str, Any]],
    ) -> bool:
        """Persist the complete row-conserving projection in one commit.

        Returns ``False`` only for a byte-equivalent already persisted batch.
        Raw counterparty/description fields are intentionally not accepted.
        """

        allowed_batch = {
            "batch_id", "tenant_digest", "company_scope_digest", "source_file_sha256",
            "adapter_id", "adapter_version", "normalization_version", "input_row_count",
            "classified_count", "unaccounted_count", "quarantined_count",
            "duplicate_linked_count", "created_at_epoch_ms", "ambiguous_columns",
        }
        if set(batch) != allowed_batch:
            raise AssignmentError("INVALID_REQUEST_SCHEMA", 422, "Batch projection fields are invalid.")
        if batch["input_row_count"] != sum(
            int(batch[name])
            for name in (
                "classified_count", "unaccounted_count", "quarantined_count",
                "duplicate_linked_count",
            )
        ):
            raise AssignmentError("ROW_CONSERVATION_VIOLATION", 503, "The batch row counts are inconsistent.")
        expected_row_fields = {
            "row_id", "source_row_number", "source_row_fingerprint", "direction",
            "currency", "amount_minor", "booked_date", "terminal_state",
            "classification_source", "reason_code", "transaction_id",
            "duplicate_of_row_id", "vendor_token", "hmac_key_id", "account_id",
            "rule_id", "transaction_version", "created_at_epoch_ms",
        }
        if len(rows) != int(batch["input_row_count"]) or any(
            set(row) != expected_row_fields for row in rows
        ):
            raise AssignmentError("ROW_CONSERVATION_VIOLATION", 503, "The batch row projection is incomplete.")
        fingerprint = sha256_json({"batch": batch, "rows": rows, "receipts": receipts})
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                existing = conn.execute(
                    "SELECT * FROM accounting_source_batches WHERE batch_id=?",
                    (batch["batch_id"],),
                ).fetchone()
                if existing is not None:
                    existing_fingerprint = sha256_json(
                        {
                            "source_file_sha256": existing["source_file_sha256"],
                            "adapter_id": existing["adapter_id"],
                            "adapter_version": existing["adapter_version"],
                            "input_row_count": existing["input_row_count"],
                        }
                    )
                    claimed = sha256_json(
                        {
                            "source_file_sha256": batch["source_file_sha256"],
                            "adapter_id": batch["adapter_id"],
                            "adapter_version": batch["adapter_version"],
                            "input_row_count": batch["input_row_count"],
                        }
                    )
                    if existing_fingerprint != claimed:
                        raise AssignmentError(
                            "BATCH_ID_REUSE_MISMATCH", 409, "The batch identifier is already bound to other input."
                        )
                    conn.execute("COMMIT")
                    return False
                conn.execute(
                    """INSERT INTO accounting_source_batches
                       (batch_id,tenant_digest,company_scope_digest,source_file_sha256,
                        adapter_id,adapter_version,normalization_version,input_row_count,
                        classified_count,unaccounted_count,quarantined_count,
                        duplicate_linked_count,state,created_at_epoch_ms,resource_version,
                        ambiguous_columns_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'READY', ?,1,?)""",
                    (
                        batch["batch_id"], batch["tenant_digest"], batch["company_scope_digest"],
                        batch["source_file_sha256"], batch["adapter_id"], batch["adapter_version"],
                        batch["normalization_version"], batch["input_row_count"],
                        batch["classified_count"], batch["unaccounted_count"],
                        batch["quarantined_count"], batch["duplicate_linked_count"],
                        batch["created_at_epoch_ms"], stable_json(batch["ambiguous_columns"]),
                    ),
                )
                for row in rows:
                    conn.execute(
                        """INSERT INTO accounting_source_rows
                           (row_id,batch_id,source_row_number,source_row_fingerprint,direction,
                            currency,amount_minor,booked_date,terminal_state,classification_source,
                            reason_code,transaction_id,duplicate_of_row_id,vendor_token,hmac_key_id,
                            account_id,rule_id,transaction_version,created_at_epoch_ms)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            row["row_id"], batch["batch_id"], row["source_row_number"],
                            row["source_row_fingerprint"], row["direction"], row["currency"],
                            row["amount_minor"], row["booked_date"], row["terminal_state"],
                            row["classification_source"], row["reason_code"], row["transaction_id"],
                            row["duplicate_of_row_id"], row["vendor_token"], row["hmac_key_id"],
                            row["account_id"], row["rule_id"], row["transaction_version"],
                            row["created_at_epoch_ms"],
                        ),
                    )
                for receipt in receipts:
                    conn.execute(
                        """INSERT INTO rule_application_receipts
                           (receipt_id,tenant_digest,transaction_id,rule_id,source_assignment_id,
                            match_key_digest,registry_digest,classification_source,journal_posted,
                            financial_statement_effective,actor_id_digest,applied_at_epoch_ms,
                            event_hash,resource_version)
                           VALUES(?,?,?,?,?,?,?,'USER_RULE_APPLIED_DRAFT',0,0,?,?,?,1)""",
                        (
                            receipt["receipt_id"], batch["tenant_digest"], receipt["transaction_id"],
                            receipt["rule_id"], receipt["source_assignment_id"],
                            receipt["match_key_digest"], receipt["registry_digest"],
                            receipt["actor_id_digest"], receipt["applied_at_epoch_ms"],
                            receipt["event_hash"],
                        ),
                    )
                conn.execute("COMMIT")
                return True
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "PERSISTENCE_COMMIT_FAILED", 503, "The review batch was not committed."
                ) from exc

    def review_batch(self, tenant_digest: str, batch_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            batch = conn.execute(
                "SELECT * FROM accounting_source_batches WHERE tenant_digest=? AND batch_id=? AND state='READY'",
                (tenant_digest, batch_id),
            ).fetchone()
            if batch is None:
                return None
            rows = conn.execute(
                "SELECT * FROM accounting_source_rows WHERE batch_id=? ORDER BY source_row_number",
                (batch_id,),
            ).fetchall()
        result = dict(batch)
        result["rows"] = [dict(row) for row in rows]
        result["ambiguous_columns"] = json.loads(result.pop("ambiguous_columns_json"))
        return result

    def remove_review_batch(self, batch_id: str) -> None:
        """Tombstone a durable projection while preserving row lineage evidence."""

        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                conn.execute(
                    """UPDATE accounting_source_batches SET state='REMOVED',
                       resource_version=resource_version+1 WHERE batch_id=? AND state='READY'""",
                    (batch_id,),
                )
                conn.execute("COMMIT")
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "PERSISTENCE_COMMIT_FAILED", 503,
                    "The review projection could not be removed.",
                ) from exc

    def review_transaction(self, tenant_digest: str, transaction_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT r.*,b.tenant_digest,b.company_scope_digest,b.adapter_id,b.adapter_version,
                          b.normalization_version,b.resource_version AS batch_version,b.batch_id
                   FROM accounting_source_rows r
                   JOIN accounting_source_batches b ON b.batch_id=r.batch_id
                   WHERE b.tenant_digest=? AND r.transaction_id=? AND b.state='READY'""",
                (tenant_digest, transaction_id),
            ).fetchone()
            if row is None:
                return None
            batch = conn.execute(
                "SELECT * FROM accounting_source_batches WHERE batch_id=?",
                (row["batch_id"],),
            ).fetchone()
        return dict(batch), dict(row)

    def issue_action_nonce(
        self,
        *,
        tenant_digest: str,
        actor_id_digest: str,
        session_id_digest: str,
        transaction_id: str,
        action: str,
        now_epoch_ms: int,
        ttl_ms: int = 300_000,
    ) -> str:
        raw = __import__("secrets").token_urlsafe(48)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with self._lock, self._connect() as conn:
            self._begin(conn)
            conn.execute(
                """INSERT INTO accounting_action_nonces
                   (nonce_digest,tenant_digest,actor_id_digest,session_id_digest,
                    transaction_id,action,expires_at_epoch_ms)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    digest, tenant_digest, actor_id_digest, session_id_digest,
                    transaction_id, action, now_epoch_ms + ttl_ms,
                ),
            )
            conn.execute("COMMIT")
        return raw

    def quarantine_rows(self, tenant_digest: str, batch_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT r.row_id,r.batch_id,r.source_row_number,r.source_row_fingerprint,
                          r.reason_code,r.terminal_state AS state,r.transaction_version AS resource_version
                   FROM accounting_source_rows r
                   JOIN accounting_source_batches b ON b.batch_id=r.batch_id
                   WHERE b.tenant_digest=? AND r.batch_id=? AND r.terminal_state='QUARANTINED'
                   ORDER BY r.source_row_number""",
                (tenant_digest, batch_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def recompile_quarantine_row(
        self,
        *,
        tenant_digest: str,
        actor_id_digest: str,
        session_id_digest: str,
        batch_id: str,
        row_id: str,
        expected_version: int,
        correction_digest: str,
        replacement: dict[str, Any],
        idempotency_key: str,
        authority_context: TenantContext | None = None,
    ) -> dict[str, Any]:
        route_id = "POST:/v1/accounting/review/batches/{batch_id}/quarantine/{row_id}/recompile"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body_digest = sha256_json({"correction_digest": correction_digest, "replacement": replacement})
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                replay = self._idempotent_response(
                    conn, tenant_digest=tenant_digest, actor_id=actor_id_digest,
                    route_id=route_id, resource_id=row_id, key_digest=key_digest,
                    body_digest=body_digest,
                )
                if replay is not None:
                    conn.execute("COMMIT")
                    return replay
                row = conn.execute(
                    """SELECT r.*,b.tenant_digest FROM accounting_source_rows r
                       JOIN accounting_source_batches b ON b.batch_id=r.batch_id
                       WHERE r.batch_id=? AND r.row_id=?""",
                    (batch_id, row_id),
                ).fetchone()
                if row is None or row["tenant_digest"] != tenant_digest:
                    raise AssignmentError("AUTHORIZATION_DENIED", 404, "The accounting resource is unavailable.")
                if row["terminal_state"] != "QUARANTINED":
                    raise AssignmentError("TRANSACTION_NOT_REVIEWABLE", 409, "The row is no longer quarantined.")
                if int(row["transaction_version"]) != expected_version:
                    raise AssignmentError("STALE_ASSIGNMENT_VERSION", 409, "The row version is stale.")
                previous = conn.execute(
                    "SELECT event_hash FROM accounting_quarantine_events WHERE tenant_digest=? ORDER BY sequence DESC LIMIT 1",
                    (tenant_digest,),
                ).fetchone()
                previous_hash = str(previous["event_hash"]) if previous else None
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                event_id = str(uuid.uuid4())
                event_body = {
                    "event_id": event_id, "tenant_digest": tenant_digest, "batch_id": batch_id,
                    "row_id": row_id, "reason_code": "QUARANTINE_CORRECTION_REQUESTED",
                    "correction_field_digest": correction_digest,
                    "actor_id_digest": actor_id_digest, "session_id_digest": session_id_digest,
                    "previous_event_hash": previous_hash, "occurred_at_epoch_ms": now_ms,
                }
                event_hash = sha256_json(event_body)
                conn.execute(
                    """INSERT INTO accounting_quarantine_events
                       (event_id,tenant_digest,batch_id,row_id,reason_code,correction_field_digest,
                        actor_id_digest,session_id_digest,previous_event_hash,event_hash,occurred_at_epoch_ms)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id, tenant_digest, batch_id, row_id,
                        "QUARANTINE_CORRECTION_REQUESTED", correction_digest,
                        actor_id_digest, session_id_digest, previous_hash, event_hash, now_ms,
                    ),
                )
                next_version = expected_version + 1
                conn.execute(
                    """UPDATE accounting_source_rows SET amount_minor=?,booked_date=?,currency=?,
                       direction=?,terminal_state=?,classification_source=?,reason_code=?,
                       transaction_id=?,transaction_version=? WHERE row_id=?""",
                    (
                        replacement["amount_minor"], replacement["booked_date"], replacement["currency"],
                        replacement["direction"], replacement["terminal_state"],
                        replacement["classification_source"], replacement["reason_code"],
                        replacement["transaction_id"], next_version, row_id,
                    ),
                )
                conn.execute(
                    """UPDATE accounting_source_batches SET quarantined_count=quarantined_count-1,
                       unaccounted_count=unaccounted_count+?,classified_count=classified_count+?,
                       resource_version=resource_version+1 WHERE batch_id=?""",
                    (
                        1 if replacement["terminal_state"] == "UNACCOUNTED" else 0,
                        1 if replacement["terminal_state"] == "CLASSIFIED" else 0,
                        batch_id,
                    ),
                )
                response = {
                    "schema_version": "3.0", "row_id": row_id,
                    "state": replacement["terminal_state"], "resource_version": next_version,
                    "event_hash": event_hash,
                }
                conn.execute(
                    """INSERT INTO idempotency_records
                       (tenant_digest,actor_id,route_id,resource_id,key_digest,body_digest,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        tenant_digest, actor_id_digest, route_id, row_id, key_digest,
                        body_digest, stable_json(response), utc_now(),
                    ),
                )
                self._append_authorization_allow_if_present(
                    conn,
                    context=authority_context,
                    reason_code="MUTATION_COMMITTED",
                    before_hash=sha256_json(dict(row)),
                    after_hash=sha256_json(response),
                    observed_at=now_ms,
                )
                conn.execute("COMMIT")
                return response
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("PERSISTENCE_COMMIT_FAILED", 503, "The correction was not committed.") from exc

    def active_rule(
        self, tenant_digest: str, token: str, adapter_family: str, normalization: str
    ) -> dict[str, Any] | None:
        """Legacy compatibility lookup; schema-v3 active rules require exact dimensions."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM learned_rules WHERE tenant_digest=? AND vendor_match_token=?
                   AND adapter_id=? AND normalization_version=? AND state='ACTIVE_USER_RULE'""",
                (tenant_digest, token, adapter_family, normalization),
            ).fetchone()
        return dict(row) if row is not None else None

    def active_rules_exact(
        self,
        *,
        tenant_digest: str,
        company_scope_digest: str,
        vendor_token: str,
        adapter_id: str,
        adapter_version: str,
        normalization_version: str,
        direction: str,
        currency: str,
        hmac_key_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM learned_rules WHERE tenant_digest=? AND company_scope_digest=?
                   AND vendor_match_token=? AND adapter_id=? AND adapter_version=?
                   AND normalization_version=? AND direction=? AND currency=?
                   AND hmac_key_id=? AND state='ACTIVE_USER_RULE'
                   ORDER BY rule_id""",
                (
                    tenant_digest, company_scope_digest, vendor_token, adapter_id,
                    adapter_version, normalization_version, direction, currency, hmac_key_id,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def current_assignment(
        self, tenant_digest: str, txn_id: str
    ) -> dict[str, Any] | None:
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
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is missing."
                )
            expected_mac = self.tokens.checkpoint_mac(tenant_id, previous["event_hash"])
            if (
                checkpoint["sequence"] != previous["sequence"]
                or checkpoint["event_hash"] != previous["event_hash"]
                or not __import__("hmac").compare_digest(
                    expected_mac, checkpoint["checkpoint_mac"]
                )
            ):
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is invalid."
                )
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
            (
                tenant_digest,
                event_hash,
                checkpoint_mac,
                sequence,
                payload["occurred_at"],
            ),
        )
        return event_id, event_hash

    @staticmethod
    def _append_authority_bound_event(
        conn: sqlite3.Connection,
        *,
        event_id: str,
        actor_id_digest: str,
        tenant_digest: str,
        company_digest: str,
        ipc_session_digest: str,
        authorization_assertion_digest: str,
        authorization_decision_id: str,
        policy_version: int,
        policy_digest: str,
        action: str,
        resource_digest: str,
        nonce_digest: str,
        request_digest: str,
        occurred_epoch_ms: int,
    ) -> str:
        previous = conn.execute(
            "SELECT event_hash FROM accounting_authority_bound_events "
            "WHERE tenant_digest=? ORDER BY sequence DESC LIMIT 1",
            (tenant_digest,),
        ).fetchone()
        previous_hash = (
            str(previous["event_hash"])
            if previous is not None
            else sha256_json(
                {"chain": "AUTHORIZATION_GENESIS", "tenant_digest": tenant_digest}
            )
        )
        payload = {
            "event_id": event_id,
            "event_type": "ASSIGNMENT_CREATED",
            "actor_id_digest": actor_id_digest,
            "tenant_digest": tenant_digest,
            "company_digest": company_digest,
            "ipc_session_digest": ipc_session_digest,
            "authorization_assertion_digest": authorization_assertion_digest,
            "authorization_decision_id": authorization_decision_id,
            "policy_version": policy_version,
            "policy_digest": policy_digest,
            "action": action,
            "resource_digest": resource_digest,
            "nonce_digest": nonce_digest,
            "request_digest": request_digest,
            "occurred_epoch_ms": occurred_epoch_ms,
            "previous_event_hash": previous_hash,
        }
        event_hash = sha256_json(payload)
        conn.execute(
            """INSERT INTO accounting_authority_bound_events
               (event_id,event_type,actor_id_digest,tenant_digest,company_digest,
                ipc_session_digest,authorization_assertion_digest,
                authorization_decision_id,policy_version,policy_digest,action,
                resource_digest,nonce_digest,request_digest,occurred_epoch_ms,
                previous_event_hash,event_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                payload["event_type"],
                actor_id_digest,
                tenant_digest,
                company_digest,
                ipc_session_digest,
                authorization_assertion_digest,
                authorization_decision_id,
                policy_version,
                policy_digest,
                action,
                resource_digest,
                nonce_digest,
                request_digest,
                occurred_epoch_ms,
                previous_hash,
                event_hash,
            ),
        )
        return event_hash

    @staticmethod
    def _append_authorization_audit_v2(
        conn: sqlite3.Connection,
        *,
        context: TenantContext,
        reason_code: str,
        before_hash: str,
        after_hash: str,
        observed_at: int,
        decision: str = "ALLOW",
    ) -> str:
        """Append one independently replayable, raw-zero authority event.

        This method is called inside the business transaction.  SQLite failure
        therefore rolls back both the privileged write and its audit record.
        """

        previous = conn.execute(
            "SELECT sequence,event_hash FROM accounting_authorization_audit_v2 "
            "WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1",
            (context.tenant_id,),
        ).fetchone()
        sequence = (int(previous["sequence"]) + 1) if previous is not None else 1
        previous_hash = str(previous["event_hash"]) if previous is not None else "0" * 64
        event_id = uuid.uuid4().hex
        jti_hash = hashlib.sha256(
            context.authorization_decision_id.encode("utf-8")
        ).hexdigest()
        payload = {
            "schema_version": "2.0",
            "event_id": event_id,
            "sequence": sequence,
            "observed_at": observed_at,
            "actor_hash": context.actor_id_digest,
            "tenant_id": context.tenant_id,
            "company_id": context.authorization_company_id,
            "action": context.action,
            "resource_hash": context.authorization_resource_digest,
            "decision": decision,
            "reason_code": reason_code,
            "policy_digest": context.authorization_policy_digest,
            "assertion_jti_hash": jti_hash,
            "request_id": context.request_id,
            "trace_id": context.authorization_decision_id,
            "role_registry_version": context.role_registry_version,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "prev_hash": previous_hash,
        }
        event_hash = sha256_json(payload)
        conn.execute(
            """INSERT INTO accounting_authorization_audit_v2
               (event_id,observed_at,actor_hash,tenant_id,company_id,action,
                resource_hash,decision,reason_code,policy_digest,assertion_jti_hash,
                request_id,trace_id,role_registry_version,before_hash,after_hash,
                prev_hash,event_hash)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                observed_at,
                context.actor_id_digest,
                context.tenant_id,
                context.authorization_company_id,
                context.action,
                context.authorization_resource_digest,
                decision,
                reason_code,
                context.authorization_policy_digest,
                jti_hash,
                context.request_id,
                context.authorization_decision_id,
                context.role_registry_version,
                before_hash,
                after_hash,
                previous_hash,
                event_hash,
            ),
        )
        return event_hash

    @classmethod
    def _append_authorization_allow_if_present(
        cls,
        conn: sqlite3.Connection,
        *,
        context: TenantContext | None,
        reason_code: str,
        before_hash: str,
        after_hash: str,
        observed_at: int,
    ) -> None:
        # Direct runtime unit-policy calls carry no human decision and never
        # become product evidence. Product routes always supply the complete
        # authority context and must append successfully before COMMIT.
        if context is None or context.authorization_policy_version is None:
            return
        cls._append_authorization_audit_v2(
            conn,
            context=context,
            reason_code=reason_code,
            before_hash=before_hash,
            after_hash=after_hash,
            observed_at=observed_at,
        )

    def append_authorization_denial(
        self,
        *,
        tenant_id: str,
        company_id: str,
        action: str,
        resource_id: str,
        reason_code: str,
        request_id: str,
        policy_digest: str,
    ) -> None:
        """Persist a raw-zero denial observed at the product route boundary."""

        if (
            action not in _PRIVILEGED_AUTHORIZATION_ACTIONS
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", reason_code)
            or not tenant_id
            or len(tenant_id) > 128
            or not company_id
            or len(company_id) > 128
            or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", request_id)
            or not re.fullmatch(r"[0-9a-f]{64}", policy_digest)
        ):
            raise AssignmentError(
                "AUTHORIZATION_AUDIT_UNAVAILABLE",
                503,
                "The authorization denial could not be audited.",
            )
        resource_hash = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()
        no_mutation_hash = sha256_json(
            {
                "tenant_id": tenant_id,
                "company_id": company_id,
                "action": action,
                "resource_hash": resource_hash,
                "mutation": "NONE",
            }
        )
        request_actor_hash = hashlib.sha256(
            ("DENIED_ACTOR:" + request_id).encode("utf-8")
        ).hexdigest()
        context = TenantContext(
            tenant_id=tenant_id,
            tenant_digest=hashlib.sha256(
                (tenant_id + ":" + company_id).encode("utf-8")
            ).hexdigest(),
            actor_id="actor_" + request_actor_hash[:32],
            actor_id_digest=request_actor_hash,
            session_id_digest=hashlib.sha256(
                ("UNVERIFIED_SESSION:" + request_id).encode("utf-8")
            ).hexdigest(),
            device_id_digest=hashlib.sha256(
                ("UNVERIFIED_DEVICE:" + request_id).encode("utf-8")
            ).hexdigest(),
            permission_decision_digest=hashlib.sha256(
                ("DENY:" + reason_code + ":" + request_id).encode("utf-8")
            ).hexdigest(),
            permission_policy_version="authority-denial.v2",
            action=action,
            authorization_decision_id=request_id,
            authorization_policy_digest=policy_digest,
            authorization_assertion_digest=hashlib.sha256(
                ("UNVERIFIED_ASSERTION:" + request_id).encode("utf-8")
            ).hexdigest(),
            authorization_resource_digest=resource_hash,
            role_registry_version=0,
            authorization_company_id=company_id,
            request_id=request_id,
        )
        observed_at = int(datetime.now(timezone.utc).timestamp() * 1000)
        try:
            with self._lock, self._connect() as conn:
                self._begin(conn)
                self._append_authorization_audit_v2(
                    conn,
                    context=context,
                    reason_code=reason_code,
                    before_hash=no_mutation_hash,
                    after_hash=no_mutation_hash,
                    observed_at=observed_at,
                    decision="DENY",
                )
                conn.execute("COMMIT")
        except AssignmentError:
            raise
        except sqlite3.DatabaseError as exc:
            raise AssignmentError(
                "AUTHORIZATION_AUDIT_UNAVAILABLE",
                503,
                "The authorization denial could not be audited.",
            ) from exc

    def create_assignment(
        self,
        *,
        tenant_id: str,
        tenant_digest: str,
        actor_id: str,
        actor_id_digest: str,
        session_id_digest: str,
        device_id_digest: str,
        permission_decision_digest: str,
        authorization_decision_id: str,
        authorization_action: str,
        permission_policy_version: str,
        authorization_policy_version: int | None,
        authorization_policy_digest: str,
        authorization_assertion_digest: str,
        authorization_resource_digest: str,
        txn_id: str,
        batch_id: str,
        expected_version: int,
        account_id: str,
        scope: str,
        vendor_match_token: str,
        adapter_family: str,
        adapter_version: str,
        normalization_version: str,
        company_scope_digest: str,
        direction: str,
        currency: str,
        registry_digest: str,
        overlay_digest: str,
        match_key_id: str,
        assignment_id: str,
        rule_id: str | None,
        idempotency_key: str,
        user_action_nonce: str,
        body: dict[str, Any],
        authority_context: TenantContext | None = None,
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

                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                nonce_digest = hashlib.sha256(user_action_nonce.encode("utf-8")).hexdigest()
                nonce = conn.execute(
                    "SELECT * FROM accounting_action_nonces WHERE nonce_digest=?",
                    (nonce_digest,),
                ).fetchone()
                if nonce is None or (
                    nonce["tenant_digest"] != tenant_digest
                    or nonce["actor_id_digest"] != actor_id_digest
                    or nonce["session_id_digest"] != session_id_digest
                    or nonce["transaction_id"] != txn_id
                    or nonce["action"] != authorization_action
                ):
                    raise AssignmentError("NONCE_INVALID", 409, "The user action nonce is not bound to this request.")
                if int(nonce["expires_at_epoch_ms"]) < now_ms:
                    raise AssignmentError("NONCE_INVALID", 409, "The user action nonce has expired.")
                if nonce["used_at_epoch_ms"] is not None:
                    raise AssignmentError("NONCE_REUSED", 409, "The user action nonce was already used.")

                current = conn.execute(
                    "SELECT * FROM current_assignments WHERE tenant_digest=? AND txn_id=?",
                    (tenant_digest, txn_id),
                ).fetchone()
                current_version = (
                    int(current["resource_version"]) if current is not None else 1
                )
                if current_version != expected_version:
                    raise AssignmentError(
                        "STALE_ASSIGNMENT_VERSION",
                        409,
                        "The transaction changed before assignment.",
                        current_version=current_version,
                    )

                if rule_id is not None:
                    conflict = conn.execute(
                        """SELECT * FROM learned_rules WHERE tenant_digest=? AND company_scope_digest=?
                           AND vendor_match_token=? AND adapter_id=? AND adapter_version=?
                           AND normalization_version=? AND direction=? AND currency=?
                           AND hmac_key_id=? AND state='ACTIVE_USER_RULE'""",
                        (
                            tenant_digest,
                            company_scope_digest,
                            vendor_match_token,
                            adapter_family,
                            adapter_version,
                            normalization_version,
                            direction,
                            currency,
                            match_key_id,
                        ),
                    ).fetchone()
                    if conflict is not None and conflict["account_id"] != account_id:
                        conflict_id = sha256_json(
                            {
                                "tenant": tenant_digest,
                                "txn": txn_id,
                                "existing": conflict["rule_id"],
                                "body": body_digest,
                            }
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
                            "RULE_CONFLICT_REVIEW_REQUIRED",
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
                    "schema_version": "3.0",
                    "event_id": assignment_id,
                    "event_type": EventType.ASSIGNMENT_CREATED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": batch_id,
                    "txn_id": txn_id,
                    "assignment_id": assignment_id,
                    "supersedes_assignment_id": current["assignment_id"]
                    if current is not None
                    else None,
                    "rule_id": rule_id,
                    "account_id": account_id,
                    "scope": scope,
                    "actor_id": actor_id,
                    "actor_id_digest": actor_id_digest,
                    "session_id_digest": session_id_digest,
                    "device_id_digest": device_id_digest,
                    "permission_decision_digest": permission_decision_digest,
                    "permission_policy_version": permission_policy_version,
                    "action": authorization_action,
                    "nonce_digest": nonce_digest,
                    "request_digest": body_digest,
                    "occurred_at": now,
                    "resource_version": next_version,
                    "registry_digest": registry_digest,
                    "overlay_digest": overlay_digest,
                    "match_key_id": match_key_id,
                    "normalization_version": normalization_version,
                    "reason_code": "USER_CONFIRMED_ASSIGNMENT",
                    "checkpoint_id": None,
                }
                authority_fields = {
                    "authorization_decision_id": authorization_decision_id,
                    "authorization_policy_version": authorization_policy_version,
                    "authorization_policy_digest": authorization_policy_digest,
                    "authorization_assertion_digest": authorization_assertion_digest,
                    "authorization_resource_digest": authorization_resource_digest,
                }
                if all(value is not None and value != "" for value in authority_fields.values()):
                    assignment_event.update(authority_fields)
                self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=txn_id,
                    event_type=EventType.ASSIGNMENT_CREATED,
                    payload=assignment_event,
                )
                if all(value is not None and value != "" for value in authority_fields.values()):
                    self._append_authority_bound_event(
                        conn,
                        event_id=assignment_id,
                        actor_id_digest=actor_id_digest,
                        tenant_digest=tenant_digest,
                        company_digest=company_scope_digest,
                        ipc_session_digest=session_id_digest,
                        authorization_assertion_digest=authorization_assertion_digest,
                        authorization_decision_id=authorization_decision_id,
                        policy_version=authorization_policy_version,
                        policy_digest=authorization_policy_digest,
                        action=authorization_action,
                        resource_digest=authorization_resource_digest,
                        nonce_digest=nonce_digest,
                        request_digest=body_digest,
                        occurred_epoch_ms=now_ms,
                    )
                conn.execute(
                    """INSERT INTO current_assignments
                       (tenant_digest,txn_id,assignment_id,account_id,scope,resource_version,event_id)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_digest,txn_id) DO UPDATE SET
                       assignment_id=excluded.assignment_id, account_id=excluded.account_id,
                       scope=excluded.scope, resource_version=excluded.resource_version,
                       event_id=excluded.event_id""",
                    (
                        tenant_digest,
                        txn_id,
                        assignment_id,
                        account_id,
                        scope,
                        next_version,
                        assignment_id,
                    ),
                )

                if rule_id is not None:
                    rule_event_id = rule_id + "_event"
                    rule_event = {
                        **assignment_event,
                        "event_id": rule_event_id,
                        "event_type": EventType.RULE_CREATED.value,
                        "assignment_id": assignment_id,
                        "rule_id": rule_id,
                        "reason_code": "ACTIVE_USER_RULE_CREATED",
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
                            state,created_at,deactivated_at,resource_version,company_scope_digest,adapter_id,
                            adapter_version,direction,currency,hmac_key_id,created_actor_digest,
                            created_at_epoch_ms,deactivated_at_epoch_ms)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                            RuleState.ACTIVE_USER_RULE.value,
                            now,
                            None,
                            1,
                            company_scope_digest,
                            adapter_family,
                            adapter_version,
                            direction,
                            currency,
                            match_key_id,
                            actor_id_digest,
                            now_ms,
                            None,
                        ),
                    )

                response = {
                    "schema_version": "3.0",
                    "assignment_id": assignment_id,
                    "txn_id": txn_id,
                    "state": "USER_ASSIGNED",
                    "account_id": account_id,
                    "scope": scope,
                    "rule_effect": "ACTIVE_USER_RULE_CREATED"
                    if rule_id is not None
                    else "NONE",
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
                # Canonicalize the in-memory first response as well as the
                # persisted replay so an exact idempotent retry is byte-identical.
                response = json.loads(stable_json(response))
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
                nonce_update = conn.execute(
                    """UPDATE accounting_action_nonces SET used_at_epoch_ms=?,request_digest=?,
                       idempotency_digest=? WHERE nonce_digest=? AND used_at_epoch_ms IS NULL""",
                    (now_ms, body_digest, key_digest, nonce_digest),
                )
                if nonce_update.rowcount != 1:
                    raise AssignmentError("NONCE_REUSED", 409, "The user action nonce was already used.")
                conn.execute(
                    """UPDATE accounting_source_rows SET terminal_state='CLASSIFIED',
                       classification_source=?,account_id=?,rule_id=?,transaction_version=?
                       WHERE transaction_id=? AND batch_id=?""",
                    (
                        "USER_ASSIGNED_SAME_VENDOR_FUTURE" if scope == "SAME_VENDOR_FUTURE"
                        else "USER_ASSIGNED_THIS_ONLY",
                        account_id, rule_id, next_version, txn_id, batch_id,
                    ),
                )
                conn.execute(
                    """UPDATE accounting_source_batches SET unaccounted_count=unaccounted_count-1,
                       classified_count=classified_count+1,resource_version=resource_version+1
                       WHERE batch_id=?""",
                    (batch_id,),
                )
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
                self._append_authorization_allow_if_present(
                    conn,
                    context=authority_context,
                    reason_code="MUTATION_COMMITTED",
                    before_hash=sha256_json(dict(current)) if current is not None else "0" * 64,
                    after_hash=sha256_json(response),
                    observed_at=now_ms,
                )
                conn.execute("COMMIT")
                return CommitResult(response, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID",
                    503,
                    "The assignment transaction was rolled back.",
                ) from exc

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
            raise AssignmentError(
                "EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is missing."
            )
        expected = self.tokens.checkpoint_mac(tenant_id, event["event_hash"])
        if (
            event["sequence"] != checkpoint["sequence"]
            or event["event_hash"] != checkpoint["event_hash"]
            or not __import__("hmac").compare_digest(
                expected, checkpoint["checkpoint_mac"]
            )
        ):
            raise AssignmentError(
                "EVENT_CHECKPOINT_INVALID", 503, "The event checkpoint is invalid."
            )

    def revert_rule_application(
        self,
        *,
        tenant_id: str,
        tenant_digest: str,
        actor_id: str,
        actor_id_digest: str,
        session_id_digest: str,
        device_id_digest: str,
        permission_decision_digest: str,
        txn_id: str,
        expected_version: int,
        registry_digest: str,
        overlay_digest: str,
        idempotency_key: str,
        authority_context: TenantContext | None = None,
    ) -> CommitResult:
        """Revert one auto-applied draft without deleting its immutable receipt."""

        route_id = "POST:/v1/accounting/review/transactions/{txn_id}/rule-application/revert"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body_digest = sha256_json(
            {"txn_id": txn_id, "expected_transaction_version": expected_version}
        )
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

                row = conn.execute(
                    """SELECT r.*,b.tenant_digest FROM accounting_source_rows r
                       JOIN accounting_source_batches b ON b.batch_id=r.batch_id
                       WHERE r.transaction_id=? AND b.tenant_digest=?""",
                    (txn_id, tenant_digest),
                ).fetchone()
                if row is None:
                    raise AssignmentError(
                        "AUTHORIZATION_DENIED", 404,
                        "The accounting resource is unavailable.",
                    )
                if int(row["transaction_version"]) != expected_version:
                    raise AssignmentError(
                        "STALE_ASSIGNMENT_VERSION", 409,
                        "The transaction changed before the rule application was reverted.",
                        current_version=int(row["transaction_version"]),
                    )
                if (
                    row["terminal_state"] != "CLASSIFIED"
                    or row["classification_source"] != "USER_RULE_APPLIED_DRAFT"
                    or not row["rule_id"]
                ):
                    raise AssignmentError(
                        "TRANSACTION_NOT_REVIEWABLE", 409,
                        "Only an active user-rule draft can be reverted.",
                    )
                receipt = conn.execute(
                    """SELECT receipt_id FROM rule_application_receipts
                       WHERE tenant_digest=? AND transaction_id=? AND rule_id=?
                       ORDER BY applied_at_epoch_ms DESC LIMIT 1""",
                    (tenant_digest, txn_id, row["rule_id"]),
                ).fetchone()
                if receipt is None:
                    raise AssignmentError(
                        "RULE_APPLICATION_RECEIPT_INVALID", 503,
                        "The immutable rule application receipt is missing.",
                    )

                next_version = expected_version + 1
                now = utc_now()
                event = {
                    "schema_version": "3.0",
                    "event_id": str(uuid.uuid4()),
                    "event_type": EventType.RULE_APPLICATION_REVERTED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": row["batch_id"],
                    "txn_id": txn_id,
                    "assignment_id": None,
                    "supersedes_assignment_id": None,
                    "rule_id": row["rule_id"],
                    "account_id": row["account_id"],
                    "scope": "THIS_ONLY",
                    "actor_id": actor_id,
                    "actor_id_digest": actor_id_digest,
                    "session_id_digest": session_id_digest,
                    "device_id_digest": device_id_digest,
                    "permission_decision_digest": permission_decision_digest,
                    "permission_policy_version": "capability-session.v1",
                    "action": "ACCOUNTING_ASSIGN",
                    "nonce_digest": "0" * 64,
                    "request_digest": body_digest,
                    "occurred_at": now,
                    "resource_version": next_version,
                    "registry_digest": registry_digest,
                    "overlay_digest": overlay_digest,
                    "match_key_id": row["hmac_key_id"],
                    "normalization_version": None,
                    "reason_code": "USER_REVERTED_RULE_APPLICATION_DRAFT",
                    "checkpoint_id": None,
                }
                _, event_hash = self._append_event(
                    conn,
                    tenant_id=tenant_id,
                    tenant_digest=tenant_digest,
                    txn_id=txn_id,
                    event_type=EventType.RULE_APPLICATION_REVERTED,
                    payload=event,
                )
                updated = conn.execute(
                    """UPDATE accounting_source_rows SET terminal_state='UNACCOUNTED',
                       classification_source='REVIEW_REQUIRED',reason_code=?,account_id=NULL,
                       rule_id=NULL,transaction_version=?
                       WHERE row_id=? AND transaction_version=?""",
                    (
                        "USER_REVERTED_RULE_APPLICATION_DRAFT",
                        next_version,
                        row["row_id"],
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise AssignmentError(
                        "STALE_ASSIGNMENT_VERSION", 409,
                        "The transaction changed before the rule application was reverted.",
                    )
                conn.execute(
                    """UPDATE accounting_source_batches SET classified_count=classified_count-1,
                       unaccounted_count=unaccounted_count+1,resource_version=resource_version+1
                       WHERE batch_id=?""",
                    (row["batch_id"],),
                )
                response = {
                    "schema_version": "3.0",
                    "txn_id": txn_id,
                    "state": "UNACCOUNTED",
                    "transaction_version": next_version,
                    "rule_id": row["rule_id"],
                    "preserved_receipt_id": receipt["receipt_id"],
                    "event_hash": event_hash,
                }
                conn.execute(
                    """INSERT INTO idempotency_records
                       (tenant_digest,actor_id,route_id,resource_id,key_digest,body_digest,response_json,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        tenant_digest, actor_id, route_id, txn_id, key_digest,
                        body_digest, stable_json(response), now,
                    ),
                )
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
                self._append_authorization_allow_if_present(
                    conn,
                    context=authority_context,
                    reason_code="MUTATION_COMMITTED",
                    before_hash=sha256_json(dict(row)),
                    after_hash=sha256_json(response),
                    observed_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                conn.execute("COMMIT")
                return CommitResult(response, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID", 503,
                    "The rule application revert was rolled back.",
                ) from exc

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
                if (
                    payload.get("previous_event_hash") != previous
                    or sha256_json(payload) != claimed_hash
                ):
                    raise AssignmentError(
                        "EVENT_CHECKPOINT_INVALID", 503, "The event chain is invalid."
                    )
                previous = claimed_hash
            if rows:
                self._verify_checkpoint_in_transaction(conn, tenant_id, tenant_digest)
            return {
                "event_count": len(rows),
                "last_event_hash": previous,
                "passed": True,
            }

    def list_rules(
        self, tenant_digest: str, state: str | None = None
    ) -> list[dict[str, Any]]:
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
        authority_context: TenantContext | None = None,
    ) -> dict[str, Any]:
        route_id = "POST:/v1/accounting/learned-rules/{rule_id}/deactivate"
        key_digest = self.tokens.idempotency_digest(idempotency_key)
        body_digest = sha256_json(
            {"rule_id": rule_id, "expected_version": expected_version}
        )
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
                    raise AssignmentError(
                        "RULE_NOT_FOUND", 404, "The suggestion rule was not found."
                    )
                if int(row["resource_version"]) != expected_version:
                    raise AssignmentError(
                        "TRANSACTION_STALE",
                        412,
                        "The rule changed before deactivation.",
                        current_version=row["resource_version"],
                    )
                if row["state"] != RuleState.ACTIVE_USER_RULE.value:
                    raise AssignmentError(
                        "RULE_ALREADY_INACTIVE",
                        409,
                        "The suggestion rule is already inactive.",
                    )
                next_version = expected_version + 1
                now = utc_now()
                event_id = rule_id + f"_deactivate_{next_version}"
                payload = {
                    "schema_version": "3.0",
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
                response = {
                    "rule_id": rule_id,
                    "state": RuleState.INACTIVE_USER.value,
                    "resource_version": next_version,
                }
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
                self._append_authorization_allow_if_present(
                    conn,
                    context=authority_context,
                    reason_code="MUTATION_COMMITTED",
                    before_hash=sha256_json(dict(row)),
                    after_hash=sha256_json(response),
                    observed_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                conn.execute("COMMIT")
                return response
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID",
                    503,
                    "The rule transaction was rolled back.",
                ) from exc

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
        adapter_version: str,
        normalization_version: str,
        company_scope_digest: str,
        direction: str,
        currency: str,
        registry_digest: str,
        overlay_digest: str,
        match_key_id: str,
        assignment_id: str,
        replacement_rule_id: str | None,
        idempotency_key: str,
        authority_context: TenantContext | None = None,
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
                    raise AssignmentError(
                        "AUTHORIZATION_DENIED",
                        404,
                        "The accounting resource is unavailable.",
                    )
                if (
                    conflict["state"] != "OPEN"
                    or int(conflict["version"]) != expected_conflict_version
                ):
                    raise AssignmentError(
                        "CONFLICT_STALE",
                        412,
                        "The rule conflict changed before resolution.",
                        current_version=int(conflict["version"]),
                    )
                if (
                    conflict["txn_id"] != txn_id
                    or conflict["requested_account_id"] != account_id
                ):
                    raise AssignmentError(
                        "CONFLICT_EVIDENCE_INVALID",
                        503,
                        "Conflict evidence no longer matches.",
                    )
                command = json.loads(conflict["command_json"])
                if (
                    command.get("scope") != "SAME_VENDOR_FUTURE"
                    or command.get("account_id") != account_id
                ):
                    raise AssignmentError(
                        "CONFLICT_EVIDENCE_INVALID",
                        503,
                        "Conflict command evidence is invalid.",
                    )
                current = conn.execute(
                    "SELECT * FROM current_assignments WHERE tenant_digest=? AND txn_id=?",
                    (tenant_digest, txn_id),
                ).fetchone()
                current_version = (
                    int(current["resource_version"]) if current is not None else 1
                )
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
                if (
                    existing is None
                    or existing["state"] != RuleState.ACTIVE_USER_RULE.value
                ):
                    raise AssignmentError(
                        "CONFLICT_STALE", 412, "The existing rule is no longer active."
                    )
                if (
                    existing["vendor_match_token"] != vendor_match_token
                    or existing["adapter_id"] != adapter_family
                    or existing["adapter_version"] != adapter_version
                    or existing["normalization_version"] != normalization_version
                    or existing["company_scope_digest"] != company_scope_digest
                    or existing["direction"] != direction
                    or existing["currency"] != currency
                ):
                    raise AssignmentError(
                        "CONFLICT_EVIDENCE_INVALID",
                        503,
                        "Conflict match evidence is invalid.",
                    )

                now = utc_now()
                next_transaction_version = expected_transaction_version + 1
                if decision is ConflictDecision.REPLACE_WITH_NEW:
                    if replacement_rule_id is None:
                        raise AssignmentError(
                            "CONFLICT_EVIDENCE_INVALID",
                            503,
                            "Replacement rule identifier is missing.",
                        )
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
                        (
                            RuleState.INACTIVE_USER.value,
                            now,
                            old_rule_version,
                            existing["rule_id"],
                        ),
                    )

                assignment_event = {
                    "schema_version": "2.0",
                    "event_id": assignment_id,
                    "event_type": EventType.ASSIGNMENT_CREATED.value,
                    "tenant_digest": tenant_digest,
                    "batch_id": batch_id,
                    "txn_id": txn_id,
                    "assignment_id": assignment_id,
                    "supersedes_assignment_id": current["assignment_id"]
                    if current is not None
                    else None,
                    "rule_id": replacement_rule_id
                    if decision is ConflictDecision.REPLACE_WITH_NEW
                    else existing["rule_id"],
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
                            state,created_at,deactivated_at,resource_version,company_scope_digest,adapter_id,
                            adapter_version,direction,currency,hmac_key_id,created_actor_digest,
                            created_at_epoch_ms,deactivated_at_epoch_ms)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                            RuleState.ACTIVE_USER_RULE.value,
                            now,
                            None,
                            1,
                            company_scope_digest,
                            adapter_family,
                            adapter_version,
                            direction,
                            currency,
                            match_key_id,
                            hashlib.sha256(actor_id.encode("utf-8")).hexdigest(),
                            int(datetime.now(timezone.utc).timestamp() * 1000),
                            None,
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
                    "schema_version": "3.0",
                    "assignment_id": assignment_id,
                    "txn_id": txn_id,
                    "state": "USER_ASSIGNED",
                    "account_id": account_id,
                    "scope": "SAME_VENDOR_FUTURE",
                    "transaction_version": next_transaction_version,
                    "rule_effect": "ACTIVE_USER_RULE_REPLACED"
                    if decision is ConflictDecision.REPLACE_WITH_NEW
                    else "EXISTING_USER_RULE_KEPT",
                    "rule_id": replacement_rule_id
                    if decision is ConflictDecision.REPLACE_WITH_NEW
                    else existing["rule_id"],
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
                self._append_authorization_allow_if_present(
                    conn,
                    context=authority_context,
                    reason_code="MUTATION_COMMITTED",
                    before_hash=sha256_json(dict(conflict)),
                    after_hash=sha256_json(response),
                    observed_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                conn.execute("COMMIT")
                return CommitResult(response, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "EVENT_CHECKPOINT_INVALID",
                    503,
                    "The conflict transaction was rolled back.",
                ) from exc

    # ------------------------------------------------------------------
    # Box5 A4 v3.1 canonical persistence. These methods deliberately live in
    # the product's only accounting store; no parallel state database exists.
    # ------------------------------------------------------------------

    def replace_a4_own_account_registry(
        self,
        *,
        tenant_id: str,
        accounts: list[dict[str, str]],
        approval_id: str,
        observed_at: str,
    ) -> dict[str, Any]:
        """Create an immutable, bank-bound registry snapshot from an admin action."""

        self._require_a4_schema()
        try:
            uuid.UUID(tenant_id)
        except (TypeError, ValueError) as exc:
            raise AssignmentError(
                "BLOCK_REGISTRY_IDENTITY", 422, "A4 registry tenant is invalid."
            ) from exc
        if (
            not accounts
            or not isinstance(approval_id, str)
            or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", approval_id)
        ):
            raise AssignmentError(
                "BLOCK_REGISTRY_IDENTITY", 422, "A4 registry approval is invalid."
            )
        prepared: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in accounts:
            if not isinstance(item, dict) or set(item) != {
                "bank_code",
                "account_number",
            }:
                raise AssignmentError(
                    "BLOCK_REGISTRY_IDENTITY", 422, "A4 registry entry is invalid."
                )
            bank_code = re.sub(r"[^A-Z0-9._:-]", "", item["bank_code"].upper())
            account_number = re.sub(
                r"[^0-9A-Za-z]", "", item["account_number"]
            ).upper()
            if not 2 <= len(bank_code) <= 16 or not account_number:
                raise AssignmentError(
                    "BLOCK_REGISTRY_IDENTITY", 422, "A4 registry entry is invalid."
                )
            key_id, token = self.tokens.provision_a4_account_token(
                tenant_id, bank_code, account_number
            )
            identity_key = (key_id, token)
            if identity_key in seen:
                raise AssignmentError(
                    "BLOCK_REGISTRY_IDENTITY", 409, "A4 registry entry is duplicated."
                )
            seen.add(identity_key)
            account_id = self.resolve_account_identity(tenant_id, key_id, token)
            prepared.append(
                {
                    "bank_code": bank_code,
                    "account_token": token,
                    "account_id": account_id,
                    "status": "ACTIVE",
                    "effective_from": observed_at,
                    "effective_to": None,
                    "approval_id": approval_id.removeprefix("sha256:"),
                    "key_id": key_id,
                }
            )
        canonical = sorted(prepared, key=lambda row: (row["bank_code"], row["account_id"]))
        registry_version = hashlib.sha256(
            stable_json(canonical).encode("utf-8")
        ).hexdigest()
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                for row in canonical:
                    conn.execute(
                        """INSERT OR IGNORE INTO a4_own_account_registry
                           (tenant_id,registry_version,bank_code,account_token,account_id,
                            status,effective_from,effective_to,approval_id,key_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            tenant_id,
                            registry_version,
                            row["bank_code"],
                            row["account_token"],
                            row["account_id"],
                            row["status"],
                            row["effective_from"],
                            row["effective_to"],
                            row["approval_id"],
                            row["key_id"],
                        ),
                    )
                conn.execute("COMMIT")
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "BLOCK_REGISTRY_IDENTITY", 503, "A4 registry was not committed."
                ) from exc
        return self.a4_own_account_registry(tenant_id)

    def a4_own_account_registry(self, tenant_id: str) -> dict[str, Any]:
        """Return the newest complete tokenized registry; plaintext is never stored."""

        self._require_a4_schema()
        with self._connect() as conn:
            latest = conn.execute(
                """SELECT registry_version FROM a4_own_account_registry
                   WHERE tenant_id=? ORDER BY effective_from DESC,registry_version DESC
                   LIMIT 1""",
                (tenant_id,),
            ).fetchone()
            if latest is None:
                raise AssignmentError(
                    "BLOCK_REGISTRY_IDENTITY", 409, "A4 own-account registry is missing."
                )
            rows = conn.execute(
                """SELECT bank_code,account_token,account_id,status,effective_from,
                          effective_to,approval_id,key_id
                   FROM a4_own_account_registry
                   WHERE tenant_id=? AND registry_version=?
                   ORDER BY bank_code,account_id""",
                (tenant_id, latest["registry_version"]),
            ).fetchall()
        accounts = [dict(row) for row in rows]
        if len(accounts) < 2 or any(row["status"] != "ACTIVE" for row in accounts):
            raise AssignmentError(
                "BLOCK_REGISTRY_IDENTITY", 409, "A4 own-account registry is incomplete."
            )
        return {
            "schema_version": "butler.box5.a4.own_account_registry.v3.1",
            "tenant_id": tenant_id,
            "registry_version": str(latest["registry_version"]),
            "accounts": accounts,
            "registry_digest": hashlib.sha256(
                stable_json(accounts).encode("utf-8")
            ).hexdigest(),
        }

    def resolve_account_identity(
        self, tenant_id: str, lookup_key_id: str, lookup_token: str
    ) -> str:
        """Return the registry UUID for an HMAC lookup token.

        The opaque UUID is allocated once and is unrelated to bank-row order,
        aliases, or holder names.  Key rotation is performed explicitly through
        ``continue_account_identity`` so a new key cannot silently fork identity.
        """

        if not all(
            isinstance(value, str) and value
            for value in (tenant_id, lookup_key_id, lookup_token)
        ):
            raise AssignmentError(
                "A4_ACCOUNT_IDENTITY_INVALID", 422, "A4 account identity is invalid."
            )
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                row = conn.execute(
                    """SELECT account_id FROM account_identity_continuity
                       WHERE tenant_id=? AND lookup_key_id=? AND lookup_token=? AND valid_to IS NULL""",
                    (tenant_id, lookup_key_id, lookup_token),
                ).fetchone()
                if row is not None:
                    conn.execute("COMMIT")
                    return str(row["account_id"])
                account_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO account_identity_continuity
                       (tenant_id,account_id,lookup_key_id,lookup_token,valid_from,valid_to)
                       VALUES(?,?,?,?,?,NULL)""",
                    (tenant_id, account_id, lookup_key_id, lookup_token, utc_now()),
                )
                conn.execute("COMMIT")
                return account_id
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_ACCOUNT_IDENTITY_INVALID",
                    503,
                    "A4 account identity was not committed.",
                ) from exc

    def continue_account_identity(
        self,
        *,
        tenant_id: str,
        account_id: str,
        old_lookup_key_id: str,
        new_lookup_key_id: str,
        new_lookup_token: str,
    ) -> None:
        """Record an approved key-rotation mapping without changing account UUID."""

        try:
            uuid.UUID(tenant_id)
            uuid.UUID(account_id)
        except (ValueError, TypeError) as exc:
            raise AssignmentError(
                "A4_ACCOUNT_IDENTITY_INVALID", 422, "A4 account identity is invalid."
            ) from exc
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                current = conn.execute(
                    """SELECT 1 FROM account_identity_continuity
                       WHERE tenant_id=? AND account_id=? AND lookup_key_id=? AND valid_to IS NULL""",
                    (tenant_id, account_id, old_lookup_key_id),
                ).fetchone()
                if current is None:
                    raise AssignmentError(
                        "A4_ACCOUNT_IDENTITY_INVALID",
                        409,
                        "A4 continuity predecessor is missing.",
                    )
                conn.execute(
                    """INSERT INTO account_identity_continuity
                       (tenant_id,account_id,lookup_key_id,lookup_token,valid_from,valid_to)
                       VALUES(?,?,?,?,?,NULL)""",
                    (
                        tenant_id,
                        account_id,
                        new_lookup_key_id,
                        new_lookup_token,
                        utc_now(),
                    ),
                )
                conn.execute("COMMIT")
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_ACCOUNT_IDENTITY_INVALID",
                    503,
                    "A4 continuity was not committed.",
                ) from exc

    @staticmethod
    def _a4_jcs(value: Any) -> bytes:
        # Imported lazily to keep the existing assignment runtime independent
        # when A4 is disabled.
        from butler_pc_core.accounting.classify.reconciliation_v2 import jcs_bytes

        return jcs_bytes(value)

    @staticmethod
    def _a4_event_digest(
        tenant_id: str,
        run_id: str,
        sequence_no: int,
        from_state: str | None,
        to_state: str,
        reason_code: str,
        created_at: str,
    ) -> str:
        return hashlib.sha256(
            stable_json(
                {
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                    "sequence_no": sequence_no,
                    "from_state": from_state,
                    "to_state": to_state,
                    "reason_code": reason_code,
                    "created_at": created_at,
                }
            ).encode("utf-8")
        ).hexdigest()

    def _append_reconciliation_event(
        self,
        conn: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        from_state: str | None,
        to_state: str,
        reason_code: str,
        created_at: str,
    ) -> None:
        sequence_no = int(
            conn.execute(
                "SELECT COALESCE(MAX(sequence_no),0)+1 FROM recon_run_event WHERE tenant_id=? AND run_id=?",
                (tenant_id, run_id),
            ).fetchone()[0]
        )
        conn.execute(
            """INSERT INTO recon_run_event
               (tenant_id,run_id,sequence_no,from_state,to_state,reason_code,created_at,event_digest)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                tenant_id,
                run_id,
                sequence_no,
                from_state,
                to_state,
                reason_code,
                created_at,
                self._a4_event_digest(
                    tenant_id,
                    run_id,
                    sequence_no,
                    from_state,
                    to_state,
                    reason_code,
                    created_at,
                ),
            ),
        )

    def queue_reconciliation_run(self, *, run: dict[str, Any]) -> CommitResult:
        """Durably commit QUEUED before any worker handoff."""

        self._require_a4_schema()
        required = {
            "tenant_id",
            "run_id",
            "nonce",
            "nonce_digest",
            "idempotency_digest",
            "code_tree_oid",
            "input_closure_digest",
            "created_at",
        }
        if set(run) != required:
            raise AssignmentError("BLOCK_RUN_BINDING", 422, "A4 run binding is invalid.")
        tenant_id, run_id, created_at = run["tenant_id"], run["run_id"], run["created_at"]
        try:
            uuid.UUID(tenant_id)
            uuid.UUID(run_id)
        except (TypeError, ValueError) as exc:
            raise AssignmentError("BLOCK_RUN_BINDING", 422, "A4 run binding is invalid.") from exc
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                prior = conn.execute(
                    "SELECT nonce_digest,input_closure_digest,state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if prior is not None:
                    if (prior["nonce_digest"], prior["input_closure_digest"]) != (
                        run["nonce_digest"],
                        run["input_closure_digest"],
                    ):
                        raise AssignmentError("IDEMPOTENCY_CONFLICT", 409, "A4 queue binding conflicts.")
                    conn.execute("COMMIT")
                    return CommitResult({"run_id": run_id, "state": prior["state"]}, True)
                conn.execute(
                    """INSERT INTO recon_run
                       (tenant_id,run_id,nonce,nonce_digest,idempotency_digest,state,code_tree_oid,
                        input_closure_digest,created_at,updated_at)
                       VALUES(?,?,?,?,?,'QUEUED',?,?,?,?)""",
                    (
                        tenant_id,
                        run_id,
                        run["nonce"],
                        run["nonce_digest"],
                        run["idempotency_digest"],
                        run["code_tree_oid"],
                        run["input_closure_digest"],
                        created_at,
                        created_at,
                    ),
                )
                conn.execute(
                    "INSERT INTO a4_job(tenant_id,run_id,available_at) VALUES(?,?,?)",
                    (tenant_id, run_id, created_at),
                )
                self._append_reconciliation_event(
                    conn,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    from_state=None,
                    to_state="QUEUED",
                    reason_code="REQUEST_ACCEPTED",
                    created_at=created_at,
                )
                conn.execute("COMMIT")
                return CommitResult({"run_id": run_id, "state": "QUEUED"}, False)
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, OSError, KeyError, TypeError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("BLOCK_STATE_TRANSITION", 503, "A4 queue was not committed.") from exc

    def claim_reconciliation_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_owner_digest: str,
        observed_at: str,
        lease_expires_at: str,
    ) -> int:
        """Lease and enter RUNNING with a monotonic fencing token."""

        self._require_a4_schema()
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                row = conn.execute(
                    "SELECT state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if row is None or row["state"] != "QUEUED":
                    raise AssignmentError("BLOCK_STATE_TRANSITION", 409, "A4 run is not claimable.")
                conn.execute(
                    """UPDATE a4_job SET lease_owner_digest=?,lease_token=lease_token+1,
                       lease_expires_at=?,heartbeat_at=?,attempt_no=attempt_no+1
                       WHERE tenant_id=? AND run_id=?""",
                    (worker_owner_digest, lease_expires_at, observed_at, tenant_id, run_id),
                )
                token = int(conn.execute(
                    "SELECT lease_token FROM a4_job WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()[0])
                for previous, target, reason in (
                    ("QUEUED", "LEASED", "WORKER_LEASED"),
                    ("LEASED", "RUNNING", "WORKER_STARTED"),
                ):
                    conn.execute(
                        "UPDATE recon_run SET state=?,version=version+1,updated_at=? WHERE tenant_id=? AND run_id=? AND state=?",
                        (target, observed_at, tenant_id, run_id, previous),
                    )
                    self._append_reconciliation_event(
                        conn,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        from_state=previous,
                        to_state=target,
                        reason_code=reason,
                        created_at=observed_at,
                    )
                conn.execute("COMMIT")
                return token
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError("BLOCK_STATE_TRANSITION", 503, "A4 lease was not committed.") from exc

    def recover_expired_reconciliation_jobs(self, *, observed_at: str) -> int:
        """Return expired fenced jobs to QUEUED without losing their run history."""

        self._require_a4_schema()
        recovered = 0
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                rows = conn.execute(
                    """SELECT r.tenant_id,r.run_id,r.state FROM recon_run r
                       JOIN a4_job j ON j.tenant_id=r.tenant_id AND j.run_id=r.run_id
                       WHERE r.state IN ('LEASED','RUNNING')
                         AND j.lease_expires_at IS NOT NULL AND j.lease_expires_at<=?
                       ORDER BY r.tenant_id,r.run_id""",
                    (observed_at,),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        """UPDATE recon_run SET state='QUEUED',version=version+1,updated_at=?
                           WHERE tenant_id=? AND run_id=? AND state=?""",
                        (observed_at, row["tenant_id"], row["run_id"], row["state"]),
                    )
                    conn.execute(
                        """UPDATE a4_job SET lease_owner_digest=NULL,lease_expires_at=NULL,
                           heartbeat_at=NULL,available_at=? WHERE tenant_id=? AND run_id=?""",
                        (observed_at, row["tenant_id"], row["run_id"]),
                    )
                    self._append_reconciliation_event(
                        conn,
                        tenant_id=row["tenant_id"],
                        run_id=row["run_id"],
                        from_state=row["state"],
                        to_state="QUEUED",
                        reason_code="LEASE_EXPIRED_RECOVERY",
                        created_at=observed_at,
                    )
                    recovered += 1
                conn.execute("COMMIT")
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "BLOCK_STATE_TRANSITION", 503, "A4 recovery was not committed."
                ) from exc
        return recovered

    def terminate_reconciliation_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        error_code: str,
        observed_at: str,
    ) -> None:
        """Commit one terminal failure for a worker-visible A4 run."""

        self._require_a4_schema()
        if not re.fullmatch(r"(?:BLOCK|KEYCHAIN)_[A-Z0-9_]+", error_code):
            error_code = "BLOCK_INTERNAL"
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                row = conn.execute(
                    "SELECT state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if row is None:
                    raise AssignmentError("BLOCK_STATE_TRANSITION", 404, "A4 run is missing.")
                previous = str(row["state"])
                if previous in {"BLOCKED", "FAILED", "CANCELLED", "PUBLISHED"}:
                    conn.execute("COMMIT")
                    return
                target = (
                    "BLOCKED"
                    if previous in {"EVIDENCE_STAGED", "VERIFYING", "VERIFIED"}
                    else "FAILED"
                )
                conn.execute(
                    """UPDATE recon_run SET state=?,error_code=?,version=version+1,updated_at=?
                       WHERE tenant_id=? AND run_id=? AND state=?""",
                    (target, error_code, observed_at, tenant_id, run_id, previous),
                )
                self._append_reconciliation_event(
                    conn,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    from_state=previous,
                    to_state=target,
                    reason_code=error_code,
                    created_at=observed_at,
                )
                conn.execute("COMMIT")
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "BLOCK_STATE_TRANSITION", 503, "A4 terminal state was not committed."
                ) from exc

    def commit_reconciliation_run(
        self,
        *,
        run: dict[str, Any],
        transactions: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        classifications: list[dict[str, Any]],
        policy_receipt: dict[str, Any],
        evidence_payloads: dict[str, bytes],
    ) -> CommitResult:
        """Commit result, exact evidence bytes, and outbox in one transaction."""

        self._require_a4_schema()
        tenant_id, run_id = run.get("tenant_id"), run.get("run_id")
        if (
            not isinstance(tenant_id, str)
            or not isinstance(run_id, str)
            or not evidence_payloads
        ):
            raise AssignmentError("A4_EVIDENCE_INVALID", 422, "A4 evidence is invalid.")
        expected = {
            path: hashlib.sha256(payload).hexdigest()
            for path, payload in evidence_payloads.items()
        }
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                prior = conn.execute(
                    "SELECT nonce_digest,code_tree_oid,input_closure_digest,state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if prior is None:
                    raise AssignmentError(
                        "BLOCK_STATE_TRANSITION", 409, "A4 run was not durably queued."
                    )
                if tuple(prior[key] for key in ("nonce_digest", "code_tree_oid", "input_closure_digest")) != (
                        run["nonce_digest"],
                        run["code_tree_oid"],
                        run["input_closure_digest"],
                ):
                    raise AssignmentError(
                        "IDEMPOTENCY_CONFLICT", 409, "A4 run binding conflicts."
                    )
                if prior["state"] in {
                    "EVIDENCE_STAGED", "VERIFYING", "VERIFIED", "PUBLISHED"
                }:
                    rows = conn.execute(
                        "SELECT path,sha256,payload_jcs FROM recon_evidence_payload WHERE tenant_id=? AND run_id=?",
                        (tenant_id, run_id),
                    ).fetchall()
                    observed = {
                        str(row["path"]): (
                            str(row["sha256"]),
                            bytes(row["payload_jcs"]),
                        )
                        for row in rows
                    }
                    if set(observed) != set(evidence_payloads) or any(
                        observed[path][0] != expected[path]
                        or observed[path][1] != evidence_payloads[path]
                        for path in evidence_payloads
                    ):
                        raise AssignmentError(
                            "IDEMPOTENCY_CONFLICT", 409, "A4 evidence replay conflicts."
                        )
                    conn.execute("COMMIT")
                    return CommitResult(
                        {"run_id": run_id, "state": prior["state"]}, True
                    )
                if prior["state"] != "RUNNING":
                    raise AssignmentError(
                        "BLOCK_STATE_TRANSITION", 409, "A4 run is not running."
                    )
                for item in transactions:
                    existing_tx = conn.execute(
                        "SELECT * FROM recon_transaction WHERE tenant_id=? AND txn_uid=?",
                        (tenant_id, item["txn_uid"]),
                    ).fetchone()
                    immutable_columns = (
                        "source_row_digest",
                        "row_ordinal",
                        "row_locator",
                        "canonical_row_digest",
                        "account_id",
                        "resolved_counterparty_account_id",
                        "counterparty_resolution",
                        "direction",
                        "amount_minor",
                        "currency",
                        "booked_at_utc",
                        "local_date",
                        "value_date",
                        "bank_code",
                        "bank_reference_token",
                        "duplicate_of_reference_token",
                        "reversal_of_reference_token",
                        "counterparty_account_token",
                        "row_kind",
                        "product_code_id",
                        "channel_id",
                        "adapter_id",
                        "adapter_digest",
                        "registry_digest",
                    )
                    identity = {
                        "source_row_digest": item["source_row_digest"],
                        "row_ordinal": item["row_ordinal"],
                        "row_locator": f"row:{item['row_ordinal']}",
                        "canonical_row_digest": item["canonical_row_digest"],
                        "account_id": item["account_id"],
                        "resolved_counterparty_account_id": item.get(
                            "resolved_counterparty_account_id"
                        ),
                        "counterparty_resolution": item["counterparty_resolution"],
                        "direction": item["direction"],
                        "amount_minor": item["amount_minor"],
                        "currency": item["currency"],
                        "booked_at_utc": item["booked_at_utc"],
                        "local_date": item["local_date"],
                        "value_date": item.get("value_date"),
                        "bank_code": item["bank_code"],
                        "bank_reference_token": item.get("bank_reference_token"),
                        "duplicate_of_reference_token": item.get(
                            "duplicate_of_reference_token"
                        ),
                        "reversal_of_reference_token": item.get(
                            "reversal_of_reference_token"
                        ),
                        "counterparty_account_token": item.get(
                            "counterparty_account_token"
                        ),
                        "row_kind": item["row_kind"],
                        "product_code_id": item["product_code_id"],
                        "channel_id": item["channel_id"],
                        "adapter_id": item["adapter_id"],
                        "adapter_digest": item["adapter_digest"],
                        "registry_digest": item["registry_digest"],
                    }
                    if existing_tx is None:
                        conn.execute(
                            """INSERT INTO recon_transaction
                               (tenant_id,txn_uid,source_row_digest,row_ordinal,row_locator,
                                canonical_row_digest,account_id,
                                resolved_counterparty_account_id,counterparty_resolution,
                                direction,amount_minor,currency,booked_at_utc,local_date,bank_code,
                                value_date,bank_reference_token,duplicate_of_reference_token,
                                reversal_of_reference_token,counterparty_account_token,row_kind,
                                product_code_id,channel_id,adapter_id,adapter_digest,registry_digest)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                tenant_id,
                                item["txn_uid"],
                                item["source_row_digest"],
                                item["row_ordinal"],
                                f"row:{item['row_ordinal']}",
                                item["canonical_row_digest"],
                                item["account_id"],
                                item.get("resolved_counterparty_account_id"),
                                item["counterparty_resolution"],
                                item["direction"],
                                item["amount_minor"],
                                item["currency"],
                                item["booked_at_utc"],
                                item["local_date"],
                                item["bank_code"],
                                item.get("value_date"),
                                item.get("bank_reference_token"),
                                item.get("duplicate_of_reference_token"),
                                item.get("reversal_of_reference_token"),
                                item.get("counterparty_account_token"),
                                item["row_kind"],
                                item["product_code_id"],
                                item["channel_id"],
                                item["adapter_id"],
                                item["adapter_digest"],
                                item["registry_digest"],
                            ),
                        )
                    elif any(
                        existing_tx[column] != identity[column]
                        for column in immutable_columns
                    ):
                        raise AssignmentError(
                            "IDEMPOTENCY_CONFLICT",
                            409,
                            "A4 transaction identity conflicts.",
                        )
                    conn.execute(
                        """INSERT INTO recon_run_transaction
                           (tenant_id,run_id,txn_uid,artifact_token) VALUES(?,?,?,?)""",
                        (tenant_id, run_id, item["txn_uid"], item["artifact_token"]),
                    )
                for item in edges:
                    outflow_ids = list(
                        item.get("outflow_txn_uids") or [item["outflow_txn_uid"]]
                    )
                    inflow_ids = list(
                        item.get("inflow_txn_uids") or [item["inflow_txn_uid"]]
                    )
                    left, right = sorted(
                        (item["outflow_txn_uid"], item["inflow_txn_uid"])
                    )
                    match_type = item.get("match_type") or (
                        "FEE_ADJUSTED"
                        if item["fee_mode"] != "NO_FEE"
                        else "EXACT"
                    )
                    conn.execute(
                        """INSERT INTO recon_edge
                               (tenant_id,run_id,edge_id,left_txn_uid,right_txn_uid,fee_txn_uid,fee_mode,
                            fee_minor,eligibility_basis,binding_digest,candidate_digest,cost_tuple_jcs,
                            match_type,currency_mode,fx_rule_id,fx_receipt_digest,principal_count)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            tenant_id,
                            run_id,
                            item["edge_id"],
                            left,
                            right,
                            item.get("fee_txn_uid"),
                            item["fee_mode"],
                            item["fee_minor"],
                            item["eligibility_basis"],
                            item["binding_digest"],
                            item["edge_id"],
                            self._a4_jcs(
                                [item["time_delta_ms"], -int(item["exact_reference"])]
                            ),
                            match_type,
                            item.get("currency_mode") or item["currency"],
                            item.get("fx_rule_id"),
                            item.get("fx_receipt_digest"),
                            len(outflow_ids) + len(inflow_ids),
                        ),
                    )
                    members = [
                        *(('OUTFLOW', ordinal, txn_uid) for ordinal, txn_uid in enumerate(outflow_ids)),
                        *(('INFLOW', ordinal, txn_uid) for ordinal, txn_uid in enumerate(inflow_ids)),
                    ]
                    if item.get("fee_txn_uid"):
                        members.append(("FEE", 0, item["fee_txn_uid"]))
                    for role, ordinal, txn_uid in members:
                        conn.execute(
                            """INSERT INTO recon_edge_member
                               (tenant_id,run_id,edge_id,txn_uid,member_role,member_ordinal)
                               VALUES(?,?,?,?,?,?)""",
                            (tenant_id, run_id, item["edge_id"], txn_uid, role, ordinal),
                        )
                for item in classifications:
                    conn.execute(
                        """INSERT INTO recon_classification
                           (tenant_id,run_id,classification_id,kind,affects_reporting,payload_digest)
                           VALUES(?,?,?,?,0,?)""",
                        (
                            tenant_id,
                            run_id,
                            item["classification_id"],
                            item["kind"],
                            item["payload_digest"],
                        ),
                    )
                conn.execute(
                    """INSERT INTO recon_policy_receipt
                       (tenant_id,run_id,policy_id,policy_digest,signer_key_id,signature)
                       VALUES(?,?,?,?,?,?)""",
                    (
                        tenant_id,
                        run_id,
                        policy_receipt["policy_id"],
                        policy_receipt["policy_digest"],
                        policy_receipt["signer_key_id"],
                        policy_receipt["signature_b64"],
                    ),
                )
                for sequence, path in enumerate(sorted(evidence_payloads), start=1):
                    payload = evidence_payloads[path]
                    conn.execute(
                        """INSERT INTO recon_evidence_payload
                           (tenant_id,run_id,path,payload_jcs,sha256) VALUES(?,?,?,?,?)""",
                        (tenant_id, run_id, path, payload, expected[path]),
                    )
                    conn.execute(
                        """INSERT INTO recon_outbox
                           (tenant_id,run_id,seq,path,expected_sha256,state,attempts)
                           VALUES(?,?,?,?,?,'PENDING',0)""",
                        (tenant_id, run_id, sequence, path, expected[path]),
                    )
                observed_at = run["created_at"]
                conn.execute(
                    """UPDATE recon_run SET state='EVIDENCE_STAGED',policy_digest=?,adapter_digest=?,
                       dictionary_digest=?,registry_digest=?,version=version+1,updated_at=?
                       WHERE tenant_id=? AND run_id=? AND state='RUNNING'""",
                    (
                        policy_receipt["policy_digest"],
                        transactions[0]["adapter_digest"],
                        run["dictionary_digest"],
                        transactions[0]["registry_digest"],
                        observed_at,
                        tenant_id,
                        run_id,
                    ),
                )
                self._append_reconciliation_event(
                    conn,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    from_state="RUNNING",
                    to_state="EVIDENCE_STAGED",
                    reason_code="EVIDENCE_COMMITTED",
                    created_at=observed_at,
                )
                conn.execute("COMMIT")
                return CommitResult(
                    {"run_id": run_id, "state": "EVIDENCE_STAGED"}, False
                )
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (KeyError, TypeError, sqlite3.DatabaseError, OSError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_EVIDENCE_INVALID", 503, "A4 run transaction was rolled back."
                ) from exc

    def reconciliation_payloads(self, tenant_id: str, run_id: str) -> dict[str, bytes]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT path,payload_jcs,sha256 FROM recon_evidence_payload WHERE tenant_id=? AND run_id=? ORDER BY path",
                (tenant_id, run_id),
            ).fetchall()
        payloads: dict[str, bytes] = {}
        for row in rows:
            payload = bytes(row["payload_jcs"])
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise AssignmentError(
                    "A4_EVIDENCE_INVALID", 503, "A4 payload digest is invalid."
                )
            payloads[str(row["path"])] = payload
        return payloads

    def mark_reconciliation_exported(self, tenant_id: str, run_id: str) -> None:
        """Mark outbox bytes staged; verification is still required for publication."""

        self._require_a4_schema()
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                states = conn.execute(
                    "SELECT state,COUNT(*) AS count FROM recon_outbox WHERE tenant_id=? AND run_id=? GROUP BY state",
                    (tenant_id, run_id),
                ).fetchall()
                state_counts = {str(row["state"]): int(row["count"]) for row in states}
                run_row = conn.execute(
                    "SELECT state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if run_row is None or not state_counts:
                    raise AssignmentError(
                        "IDEMPOTENCY_CONFLICT", 409, "A4 outbox is missing."
                    )
                if set(state_counts) == {"STAGED"} and run_row["state"] in {
                    "EVIDENCE_STAGED", "VERIFYING", "VERIFIED", "PUBLISHED"
                }:
                    conn.execute("COMMIT")
                    return
                if (
                    set(state_counts) != {"PENDING"}
                    or run_row["state"] != "EVIDENCE_STAGED"
                ):
                    raise AssignmentError(
                        "IDEMPOTENCY_CONFLICT", 409, "A4 outbox has conflicting state."
                    )
                conn.execute(
                    "UPDATE recon_outbox SET state='STAGED',attempts=attempts+1 WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                )
                conn.execute("COMMIT")
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_EVIDENCE_INVALID", 503, "A4 export state was not committed."
                ) from exc

    def mark_reconciliation_verified(
        self, tenant_id: str, run_id: str, receipt: dict[str, Any]
    ) -> None:
        """Bind verifier PASS receipt, then publish in the same transaction."""

        from butler_pc_core.accounting.classify.verifier_authority import (
            load_authority_trust,
            verify_authority_receipt_signature,
        )

        self._require_a4_schema()
        required = {
            "schema_version", "contract_id", "run_id", "nonce", "decision",
            "reason_codes", "source_sha256", "ordered_row_root",
            "compiled_manifest_digest", "graph_digest", "evidence_manifest_digest",
            "policy_digest", "adapter_digest", "dictionary_digest", "registry_digest",
            "code_tree_oid", "code_closure_digest", "verifier_id", "protocol_version",
            "authority_session_id", "authority_request_id", "authority_nonce_digest",
            "caller_cdhash", "authority_cdhash", "verifier_cdhash",
            "request_digest", "source_payload_digest",
            "request_deadline_unix_ms", "signer_key_id", "authority_id",
            "signer_key_epoch", "signer_trust_digest",
            "verified_at_utc", "signature",
        }
        if (
            set(receipt) != required
            or receipt.get("schema_version")
            != "butler.box5.a4.verification_receipt.v5.3"
            or receipt.get("contract_id")
            != "BUTLER-BOX5-A4-V5.3-NATIVE-AUTHORITY"
            or receipt.get("run_id") != run_id
            or receipt.get("decision") != "PASS"
            or receipt.get("reason_codes") != []
            or not isinstance(receipt.get("signer_key_epoch"), int)
            or isinstance(receipt.get("signer_key_epoch"), bool)
            or int(receipt["signer_key_epoch"]) < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("signer_trust_digest", "")))
            or not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", str(receipt.get("authority_id", "")))
        ):
            raise AssignmentError("BLOCK_RECEIPT_BINDING", 422, "A4 receipt is invalid.")
        try:
            trust = load_authority_trust(
                self._a4_authority_trust_path,
                now=datetime.now(timezone.utc),
                allow_test_authority=self._a4_allow_test_authority,
            )
            verified_receipt = verify_authority_receipt_signature(receipt, trust)
        except Exception as exc:
            raise AssignmentError(
                "BLOCK_RECEIPT_BINDING", 422, "A4 receipt signature is invalid."
            ) from exc
        receipt_jcs = self._a4_jcs(verified_receipt)
        receipt_digest = hashlib.sha256(receipt_jcs).hexdigest()
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                row = conn.execute(
                    "SELECT state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if row is None or row["state"] not in {
                    "EVIDENCE_STAGED", "VERIFYING", "VERIFIED", "PUBLISHED"
                }:
                    raise AssignmentError(
                        "IDEMPOTENCY_CONFLICT", 409, "A4 verifier state conflicts."
                    )
                if row["state"] == "PUBLISHED":
                    existing = conn.execute(
                        "SELECT receipt_digest FROM recon_verification_receipt WHERE tenant_id=? AND run_id=?",
                        (tenant_id, run_id),
                    ).fetchone()
                    if existing is None or existing["receipt_digest"] != receipt_digest:
                        raise AssignmentError("IDEMPOTENCY_CONFLICT", 409, "A4 receipt conflicts.")
                    conn.execute("COMMIT")
                    return
                now = str(receipt["verified_at_utc"])
                if row["state"] == "EVIDENCE_STAGED":
                    conn.execute(
                        "UPDATE recon_run SET state='VERIFYING',version=version+1,updated_at=? WHERE tenant_id=? AND run_id=?",
                        (now, tenant_id, run_id),
                    )
                    self._append_reconciliation_event(
                        conn, tenant_id=tenant_id, run_id=run_id,
                        from_state="EVIDENCE_STAGED", to_state="VERIFYING",
                        reason_code="VERIFIER_STARTED", created_at=now,
                    )
                run = conn.execute(
                    "SELECT nonce,state FROM recon_run WHERE tenant_id=? AND run_id=?",
                    (tenant_id, run_id),
                ).fetchone()
                if run is None or run["nonce"] != receipt["nonce"]:
                    raise AssignmentError("BLOCK_RECEIPT_BINDING", 409, "A4 receipt nonce conflicts.")
                conn.execute(
                    """INSERT INTO recon_verification_receipt
                       (tenant_id,run_id,receipt_digest,nonce,evidence_manifest_digest,
                        verifier_id,signer_key_id,authority_id,signer_revocation_epoch,
                        signer_trust_digest,code_closure_digest,decision,verified_at,receipt_jcs)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tenant_id, run_id, receipt_digest, receipt["nonce"],
                        receipt["evidence_manifest_digest"], receipt["verifier_id"],
                        receipt["signer_key_id"], receipt["authority_id"],
                        receipt["signer_key_epoch"], receipt["signer_trust_digest"],
                        receipt["code_closure_digest"], receipt["decision"], now, receipt_jcs,
                    ),
                )
                conn.execute(
                    "UPDATE recon_run SET state='VERIFIED',version=version+1,updated_at=? WHERE tenant_id=? AND run_id=? AND state='VERIFYING'",
                    (now, tenant_id, run_id),
                )
                self._append_reconciliation_event(
                    conn, tenant_id=tenant_id, run_id=run_id, from_state="VERIFYING",
                    to_state="VERIFIED", reason_code="VERIFIER_PASS", created_at=now,
                )
                conn.execute(
                    "UPDATE recon_run SET state='PUBLISHED',version=version+1,updated_at=? WHERE tenant_id=? AND run_id=? AND state='VERIFIED'",
                    (now, tenant_id, run_id),
                )
                self._append_reconciliation_event(
                    conn, tenant_id=tenant_id, run_id=run_id, from_state="VERIFIED",
                    to_state="PUBLISHED", reason_code="RECEIPT_BOUND", created_at=now,
                )
                conn.execute("COMMIT")
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except sqlite3.DatabaseError as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_EVIDENCE_INVALID", 503, "A4 verifier state was not committed."
                ) from exc

    def reconciliation_run(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM recon_run WHERE tenant_id=? AND run_id=?",
                (tenant_id, run_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def _require_current_a4_authority_receipt(
        self, row: sqlite3.Row | None
    ) -> dict[str, Any]:
        """Revalidate a published receipt against current trust and revocation.

        Publication is not a permanent trust grant. Every candidate read and
        review mutation reopens the no-follow trust document and verifies the
        stored receipt with the currently approved key, epoch, validity window,
        and trust digest. A disabled, expired, replaced, or unavailable trust
        document therefore quarantines the published result at the access
        boundary without mutating append-only evidence.
        """

        from butler_pc_core.accounting.classify.reconciliation_v2 import (
            strict_json_loads,
        )
        from butler_pc_core.accounting.classify.verifier_authority import (
            load_authority_trust,
            verify_authority_receipt_signature,
        )

        try:
            if row is None:
                raise ValueError("missing receipt")
            receipt_jcs = bytes(row["receipt_jcs"])
            if hashlib.sha256(receipt_jcs).hexdigest() != row["receipt_digest"]:
                raise ValueError("receipt digest mismatch")
            receipt = strict_json_loads(receipt_jcs)
            if not isinstance(receipt, dict):
                raise ValueError("receipt is not an object")
            trust = load_authority_trust(
                self._a4_authority_trust_path,
                now=datetime.now(timezone.utc),
                allow_test_authority=self._a4_allow_test_authority,
            )
            return verify_authority_receipt_signature(receipt, trust)
        except Exception as exc:
            raise AssignmentError(
                "BLOCK_UNVERIFIED_ACCESS",
                409,
                "A4 publication is not trusted by the current authority policy.",
            ) from exc

    def reconciliation_candidates(
        self, tenant_id: str, run_id: str
    ) -> list[dict[str, Any]]:
        self._require_a4_schema()
        with self._connect() as conn:
            authorized = conn.execute(
                """SELECT v.receipt_digest,v.receipt_jcs FROM recon_run r
                   JOIN recon_verification_receipt v
                     ON v.tenant_id=r.tenant_id AND v.run_id=r.run_id
                   WHERE r.tenant_id=? AND r.run_id=? AND r.state='PUBLISHED'
                     AND v.decision='PASS' AND v.nonce=r.nonce
                     AND length(v.authority_id)>=3 AND v.signer_revocation_epoch>=0
                     AND length(v.signer_trust_digest)=64""",
                (tenant_id, run_id),
            ).fetchone()
            if authorized is None:
                raise AssignmentError(
                    "BLOCK_UNVERIFIED_ACCESS", 409, "A4 candidates are not verified."
                )
            self._require_current_a4_authority_receipt(authorized)
            rows = conn.execute(
                """SELECT e.edge_id,e.left_txn_uid,e.right_txn_uid,e.fee_txn_uid,e.fee_mode,
                          e.fee_minor,e.eligibility_basis,e.binding_digest,e.match_type,
                          e.currency_mode,e.fx_rule_id,e.fx_receipt_digest,e.principal_count,
                          c.kind,c.affects_reporting
                   FROM recon_edge e LEFT JOIN recon_classification c
                     ON c.tenant_id=e.tenant_id AND c.run_id=e.run_id AND c.classification_id=e.edge_id
                   WHERE e.tenant_id=? AND e.run_id=? ORDER BY e.edge_id""",
                (tenant_id, run_id),
            ).fetchall()
            members = conn.execute(
                """SELECT edge_id,txn_uid,member_role,member_ordinal
                   FROM recon_edge_member WHERE tenant_id=? AND run_id=?
                   ORDER BY edge_id,member_role,member_ordinal""",
                (tenant_id, run_id),
            ).fetchall()
        by_edge: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            by_edge.setdefault(str(member["edge_id"]), []).append(
                {
                    "txn_uid": member["txn_uid"],
                    "role": member["member_role"],
                    "ordinal": member["member_ordinal"],
                }
            )
        result = []
        for row in rows:
            item = dict(row)
            item["members"] = by_edge.get(str(row["edge_id"]), [])
            result.append(item)
        return result

    def append_reconciliation_review(
        self,
        *,
        tenant_id: str,
        run_id: str,
        edge_id: str,
        decision: str,
        actor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Append a review decision; it cannot post or affect reporting."""

        if decision not in {"ACCEPT", "REJECT", "DEFER"}:
            raise AssignmentError(
                "A4_REVIEW_INVALID", 422, "A4 review decision is invalid."
            )
        body = stable_json(
            {
                "run_id": run_id,
                "edge_id": edge_id,
                "decision": decision,
                "actor_id": actor_id,
            }
        )
        idem = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        review_id = str(
            uuid.uuid5(
                uuid.UUID(run_id), hashlib.sha256(body.encode("utf-8")).hexdigest()
            )
        )
        with self._lock, self._connect() as conn:
            self._begin(conn)
            try:
                verification = conn.execute(
                    """SELECT v.receipt_digest,v.verifier_id,v.verified_at,v.receipt_jcs
                       FROM recon_run r JOIN recon_verification_receipt v
                         ON v.tenant_id=r.tenant_id AND v.run_id=r.run_id
                       WHERE r.tenant_id=? AND r.run_id=? AND r.state='PUBLISHED'
                         AND v.decision='PASS' AND v.nonce=r.nonce
                         AND length(v.authority_id)>=3 AND v.signer_revocation_epoch>=0
                         AND length(v.signer_trust_digest)=64""",
                    (tenant_id, run_id),
                ).fetchone()
                if verification is None:
                    raise AssignmentError(
                        "BLOCK_UNVERIFIED_ACCESS", 409, "A4 review requires verified publication."
                    )
                self._require_current_a4_authority_receipt(verification)
                existing = conn.execute(
                    """SELECT review_id,edge_id,decision,actor_id FROM recon_review
                       WHERE tenant_id=? AND run_id=? AND idempotency_digest=?""",
                    (tenant_id, run_id, idem),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["edge_id"],
                        existing["decision"],
                        existing["actor_id"],
                    ) != (edge_id, decision, actor_id):
                        raise AssignmentError(
                            "IDEMPOTENCY_CONFLICT", 409, "A4 review key conflicts."
                        )
                    conn.execute("COMMIT")
                    return {
                        "review_id": existing["review_id"],
                        "replayed": True,
                        "affects_reporting": False,
                    }
                conn.execute(
                    """INSERT INTO recon_review
                       (tenant_id,run_id,review_id,edge_id,verification_receipt_digest,
                        verifier_id,verified_at,decision,actor_id,idempotency_digest,
                        affects_reporting,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                    (
                        tenant_id,
                        run_id,
                        review_id,
                        edge_id,
                        verification["receipt_digest"],
                        verification["verifier_id"],
                        verification["verified_at"],
                        decision,
                        actor_id,
                        idem,
                        utc_now(),
                    ),
                )
                conn.execute("COMMIT")
                return {
                    "review_id": review_id,
                    "replayed": False,
                    "affects_reporting": False,
                }
            except AssignmentError:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            except (sqlite3.DatabaseError, ValueError) as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise AssignmentError(
                    "A4_REVIEW_INVALID", 409, "A4 review was not appended."
                ) from exc
