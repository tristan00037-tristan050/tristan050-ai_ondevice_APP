"""Forward-only Box5 Stage3 schema migration in the canonical SQLite DB."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from .authorization_replay import (
    build_pinned_authorization_replay_schema,
    verify_authorization_replay_schema,
)


SCHEMA_VERSION = 3


def _open_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def stage3_migration_required(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with _open_read_only(path) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounting_schema_migrations'"
        ).fetchone()
        if table is None:
            return True
        return conn.execute(
            "SELECT 1 FROM accounting_schema_migrations WHERE version=?",
            (SCHEMA_VERSION,),
        ).fetchone() is None


def create_pre_migration_backup(path: Path) -> Path | None:
    """Create one durable SQLite snapshot before any Stage3 schema mutation."""

    if not stage3_migration_required(path):
        return None
    backup = path.with_name(path.name + ".pre-stage3-v3.backup.sqlite3")
    if backup.exists():
        if not backup.is_file() or backup.is_symlink():
            raise sqlite3.DatabaseError("STAGE3_BACKUP_TARGET_UNSAFE")
        with _open_read_only(backup) as existing:
            if existing.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("STAGE3_BACKUP_INVALID")
        return backup

    temporary = backup.with_name(f".{backup.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with _open_read_only(path) as source, sqlite3.connect(temporary) as target:
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("STAGE3_BACKUP_INVALID")
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, backup)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return backup
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_stage3_v3_schema(conn: sqlite3.Connection) -> None:
    """Apply an idempotent migration; unprovable legacy rules never go active."""

    replay_ddl, replay_descriptor, replay_fingerprint = (
        build_pinned_authorization_replay_schema()
    )
    try:
        conn.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS accounting_source_batches (
                batch_id TEXT PRIMARY KEY,
                tenant_digest TEXT NOT NULL,
                company_scope_digest TEXT NOT NULL,
                source_file_sha256 TEXT NOT NULL CHECK(length(source_file_sha256)=64),
                adapter_id TEXT NOT NULL,
                adapter_version TEXT NOT NULL,
                normalization_version TEXT NOT NULL,
                input_row_count INTEGER NOT NULL CHECK(input_row_count >= 0),
                classified_count INTEGER NOT NULL CHECK(classified_count >= 0),
                unaccounted_count INTEGER NOT NULL CHECK(unaccounted_count >= 0),
                quarantined_count INTEGER NOT NULL CHECK(quarantined_count >= 0),
                duplicate_linked_count INTEGER NOT NULL CHECK(duplicate_linked_count >= 0),
                state TEXT NOT NULL CHECK(state IN ('READY','REMOVED')),
                created_at_epoch_ms INTEGER NOT NULL CHECK(created_at_epoch_ms > 0),
                resource_version INTEGER NOT NULL CHECK(resource_version >= 1),
                ambiguous_columns_json TEXT NOT NULL,
                CHECK(input_row_count = classified_count + unaccounted_count + quarantined_count + duplicate_linked_count)
            );
            CREATE TABLE IF NOT EXISTS accounting_source_rows (
                row_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES accounting_source_batches(batch_id),
                source_row_number INTEGER NOT NULL CHECK(source_row_number >= 1),
                source_row_fingerprint TEXT NOT NULL CHECK(length(source_row_fingerprint)=64),
                direction TEXT CHECK(direction IS NULL OR direction IN ('IN','OUT')),
                currency TEXT CHECK(currency IS NULL OR length(currency)=3),
                amount_minor INTEGER,
                booked_date TEXT,
                terminal_state TEXT NOT NULL CHECK(terminal_state IN ('CLASSIFIED','UNACCOUNTED','QUARANTINED','DUPLICATE_LINKED')),
                classification_source TEXT,
                reason_code TEXT,
                transaction_id TEXT,
                duplicate_of_row_id TEXT,
                vendor_token TEXT CHECK(vendor_token IS NULL OR length(vendor_token)=64),
                hmac_key_id TEXT,
                account_id TEXT,
                rule_id TEXT,
                transaction_version INTEGER NOT NULL CHECK(transaction_version >= 1),
                created_at_epoch_ms INTEGER NOT NULL CHECK(created_at_epoch_ms > 0),
                UNIQUE(batch_id, source_row_number)
            );
            CREATE INDEX IF NOT EXISTS accounting_source_rows_fingerprint
              ON accounting_source_rows(batch_id,source_row_fingerprint);
            CREATE INDEX IF NOT EXISTS accounting_source_rows_txn
              ON accounting_source_rows(transaction_id);
            CREATE TABLE IF NOT EXISTS accounting_quarantine_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                tenant_digest TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                row_id TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                correction_field_digest TEXT,
                actor_id_digest TEXT,
                session_id_digest TEXT,
                previous_event_hash TEXT,
                event_hash TEXT NOT NULL UNIQUE,
                occurred_at_epoch_ms INTEGER NOT NULL CHECK(occurred_at_epoch_ms > 0)
            );
            CREATE TRIGGER IF NOT EXISTS accounting_quarantine_events_no_update
              BEFORE UPDATE ON accounting_quarantine_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_QUARANTINE'); END;
            CREATE TRIGGER IF NOT EXISTS accounting_quarantine_events_no_delete
              BEFORE DELETE ON accounting_quarantine_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_QUARANTINE'); END;
            CREATE TABLE IF NOT EXISTS rule_application_receipts (
                receipt_id TEXT PRIMARY KEY,
                tenant_digest TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                source_assignment_id TEXT NOT NULL,
                match_key_digest TEXT NOT NULL CHECK(length(match_key_digest)=64),
                registry_digest TEXT NOT NULL CHECK(length(registry_digest)=64),
                classification_source TEXT NOT NULL CHECK(classification_source='USER_RULE_APPLIED_DRAFT'),
                journal_posted INTEGER NOT NULL CHECK(journal_posted=0),
                financial_statement_effective INTEGER NOT NULL CHECK(financial_statement_effective=0),
                actor_id_digest TEXT NOT NULL CHECK(length(actor_id_digest)=64),
                applied_at_epoch_ms INTEGER NOT NULL CHECK(applied_at_epoch_ms > 0),
                event_hash TEXT NOT NULL CHECK(length(event_hash)=64),
                resource_version INTEGER NOT NULL CHECK(resource_version >= 1)
            );
            CREATE TRIGGER IF NOT EXISTS rule_application_receipts_no_update
              BEFORE UPDATE ON rule_application_receipts BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RULE_RECEIPT'); END;
            CREATE TRIGGER IF NOT EXISTS rule_application_receipts_no_delete
              BEFORE DELETE ON rule_application_receipts BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RULE_RECEIPT'); END;
            CREATE TABLE IF NOT EXISTS accounting_action_nonces (
                nonce_digest TEXT PRIMARY KEY,
                tenant_digest TEXT NOT NULL,
                actor_id_digest TEXT NOT NULL,
                session_id_digest TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                action TEXT NOT NULL,
                expires_at_epoch_ms INTEGER NOT NULL,
                used_at_epoch_ms INTEGER,
                request_digest TEXT,
                idempotency_digest TEXT
            );
            CREATE TABLE IF NOT EXISTS accounting_authority_bound_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                actor_id_digest TEXT NOT NULL CHECK(length(actor_id_digest)=64),
                tenant_digest TEXT NOT NULL CHECK(length(tenant_digest)=64),
                company_digest TEXT NOT NULL CHECK(length(company_digest)=64),
                ipc_session_digest TEXT NOT NULL CHECK(length(ipc_session_digest)=64),
                authorization_assertion_digest TEXT NOT NULL CHECK(length(authorization_assertion_digest)=64),
                authorization_decision_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL CHECK(policy_version >= 1),
                policy_digest TEXT NOT NULL CHECK(length(policy_digest)=64),
                action TEXT NOT NULL,
                resource_digest TEXT NOT NULL CHECK(length(resource_digest)=64),
                nonce_digest TEXT NOT NULL CHECK(length(nonce_digest)=64),
                request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
                occurred_epoch_ms INTEGER NOT NULL CHECK(occurred_epoch_ms > 0),
                previous_event_hash TEXT NOT NULL CHECK(length(previous_event_hash)=64),
                event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash)=64)
            );
            CREATE TRIGGER IF NOT EXISTS accounting_authority_bound_events_no_update
              BEFORE UPDATE ON accounting_authority_bound_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_AUTHORITY_EVENT'); END;
            CREATE TRIGGER IF NOT EXISTS accounting_authority_bound_events_no_delete
              BEFORE DELETE ON accounting_authority_bound_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_AUTHORITY_EVENT'); END;
            CREATE TABLE IF NOT EXISTS accounting_authorization_audit_v2 (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                observed_at INTEGER NOT NULL CHECK(observed_at > 0),
                actor_hash TEXT NOT NULL CHECK(length(actor_hash)=64),
                tenant_id TEXT NOT NULL,
                company_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_hash TEXT NOT NULL CHECK(length(resource_hash)=64),
                decision TEXT NOT NULL CHECK(decision IN ('ALLOW','DENY')),
                reason_code TEXT NOT NULL,
                policy_digest TEXT NOT NULL CHECK(length(policy_digest)=64),
                assertion_jti_hash TEXT NOT NULL CHECK(length(assertion_jti_hash)=64),
                request_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                role_registry_version INTEGER NOT NULL CHECK(role_registry_version >= 0),
                before_hash TEXT NOT NULL CHECK(length(before_hash)=64),
                after_hash TEXT NOT NULL CHECK(length(after_hash)=64),
                prev_hash TEXT NOT NULL CHECK(length(prev_hash)=64),
                event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash)=64)
            );
            CREATE TRIGGER IF NOT EXISTS accounting_authorization_audit_v2_no_update
              BEFORE UPDATE ON accounting_authorization_audit_v2 BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_AUTHORIZATION_AUDIT'); END;
            CREATE TRIGGER IF NOT EXISTS accounting_authorization_audit_v2_no_delete
              BEFORE DELETE ON accounting_authorization_audit_v2 BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_AUTHORIZATION_AUDIT'); END;
            """
            + replay_ddl
            + """
            CREATE TABLE IF NOT EXISTS accounting_schema_migrations (
                version INTEGER PRIMARY KEY,
                migration_digest TEXT NOT NULL,
                applied_at_epoch_ms INTEGER NOT NULL
            );
            """
        )
        verify_authorization_replay_schema(
            conn, replay_descriptor, replay_fingerprint
        )
        additions = {
            "company_scope_digest": "TEXT NOT NULL DEFAULT ''",
            "adapter_id": "TEXT NOT NULL DEFAULT ''",
            "adapter_version": "TEXT NOT NULL DEFAULT ''",
            "direction": "TEXT NOT NULL DEFAULT ''",
            "currency": "TEXT NOT NULL DEFAULT ''",
            "hmac_key_id": "TEXT NOT NULL DEFAULT ''",
            "created_actor_digest": "TEXT NOT NULL DEFAULT ''",
            "created_at_epoch_ms": "INTEGER NOT NULL DEFAULT 0",
            "deactivated_at_epoch_ms": "INTEGER",
        }
        current = _columns(conn, "learned_rules")
        for name, declaration in additions.items():
            if name not in current:
                conn.execute(f"ALTER TABLE learned_rules ADD COLUMN {name} {declaration}")
        # No legacy ACTIVE_SUGGESTION has the complete authenticated provenance
        # introduced by v3, so automatic promotion would be fabrication.
        conn.execute(
            "UPDATE learned_rules SET state='CONFLICT_REVIEW' WHERE state='ACTIVE_SUGGESTION'"
        )
        conn.execute("DROP INDEX IF EXISTS one_active_rule_per_token")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS one_active_user_rule_per_exact_key
               ON learned_rules(tenant_digest,company_scope_digest,vendor_match_token,
                 adapter_id,adapter_version,normalization_version,direction,currency,hmac_key_id)
               WHERE state='ACTIVE_USER_RULE'"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO accounting_schema_migrations(version,migration_digest,applied_at_epoch_ms) VALUES(3,?,CAST(strftime('%s','now') AS INTEGER)*1000)",
            ("f7772c35886c35d35abf5b159534486cd10dafd06ae86bd36f41dece101c4df3",),
        )
        fk = list(conn.execute("PRAGMA foreign_key_check"))
        if fk:
            raise sqlite3.IntegrityError("FOREIGN_KEY_CHECK_FAILED")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
