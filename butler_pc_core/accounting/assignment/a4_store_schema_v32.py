"""Canonical SQLite schema migration for the Box5 A4 v3.2 authority path."""

from __future__ import annotations

import sqlite3


_DROP_LEGACY = """
PRAGMA foreign_keys=OFF;
DROP TRIGGER IF EXISTS recon_transaction_no_update;
DROP TRIGGER IF EXISTS recon_transaction_no_delete;
DROP TRIGGER IF EXISTS recon_run_transaction_no_update;
DROP TRIGGER IF EXISTS recon_run_transaction_no_delete;
DROP TRIGGER IF EXISTS recon_edge_no_update;
DROP TRIGGER IF EXISTS recon_edge_no_delete;
DROP TRIGGER IF EXISTS recon_edge_member_no_update;
DROP TRIGGER IF EXISTS recon_edge_member_no_delete;
DROP TRIGGER IF EXISTS recon_classification_no_update;
DROP TRIGGER IF EXISTS recon_classification_no_delete;
DROP TRIGGER IF EXISTS recon_policy_receipt_no_update;
DROP TRIGGER IF EXISTS recon_policy_receipt_no_delete;
DROP TRIGGER IF EXISTS recon_review_no_update;
DROP TRIGGER IF EXISTS recon_review_no_delete;
DROP TRIGGER IF EXISTS recon_evidence_payload_no_update;
DROP TRIGGER IF EXISTS recon_evidence_payload_no_delete;
DROP TRIGGER IF EXISTS a4_attempt_event_no_update;
DROP TRIGGER IF EXISTS a4_attempt_event_no_delete;
DROP TABLE IF EXISTS recon_review;
DROP TABLE IF EXISTS recon_verification_receipt;
DROP TABLE IF EXISTS recon_outbox;
DROP TABLE IF EXISTS recon_evidence_payload;
DROP TABLE IF EXISTS recon_policy_receipt;
DROP TABLE IF EXISTS recon_classification;
DROP TABLE IF EXISTS recon_edge_member;
DROP TABLE IF EXISTS recon_edge;
DROP TABLE IF EXISTS recon_run_transaction;
DROP TABLE IF EXISTS recon_transaction;
DROP TABLE IF EXISTS a4_job;
DROP TABLE IF EXISTS recon_run_event;
DROP TABLE IF EXISTS a4_own_account_registry;
DROP TABLE IF EXISTS a4_attempt_event;
DROP TABLE IF EXISTS a4_attempt;
DROP TABLE IF EXISTS recon_run;
PRAGMA foreign_keys=ON;
"""


_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS recon_run (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    nonce_digest TEXT NOT NULL,
    idempotency_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'QUEUED','LEASED','RUNNING','EVIDENCE_STAGED','VERIFYING',
        'VERIFIED','PUBLISHED','BLOCKED','FAILED','CANCELLED')),
    code_tree_oid TEXT NOT NULL,
    input_closure_digest TEXT NOT NULL,
    policy_digest TEXT,
    adapter_digest TEXT,
    dictionary_digest TEXT,
    registry_digest TEXT,
    error_code TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (tenant_id, idempotency_digest)
);
CREATE TABLE IF NOT EXISTS recon_run_event (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    event_digest TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, sequence_no),
    UNIQUE (tenant_id, run_id, event_digest),
    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
);
CREATE TABLE IF NOT EXISTS a4_job (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    lease_owner_digest TEXT,
    lease_token INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    attempt_no INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
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
CREATE TABLE IF NOT EXISTS a4_own_account_registry (
    tenant_id TEXT NOT NULL,
    registry_version TEXT NOT NULL,
    bank_code TEXT NOT NULL,
    account_token TEXT NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','INACTIVE','REVOKED')),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    approval_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, registry_version, bank_code, account_token, effective_from),
    UNIQUE (tenant_id, registry_version, account_id, effective_from)
);
CREATE TABLE IF NOT EXISTS recon_transaction (
    tenant_id TEXT NOT NULL,
    txn_uid TEXT NOT NULL,
    source_row_digest TEXT NOT NULL,
    row_ordinal INTEGER NOT NULL CHECK(row_ordinal >= 0),
    row_locator TEXT NOT NULL,
    canonical_row_digest TEXT NOT NULL,
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
    bank_code TEXT NOT NULL,
    bank_reference_token TEXT,
    duplicate_of_reference_token TEXT,
    reversal_of_reference_token TEXT,
    counterparty_account_token TEXT,
    row_kind TEXT NOT NULL CHECK(row_kind IN ('PRINCIPAL','FEE')),
    product_code_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    adapter_digest TEXT NOT NULL,
    registry_digest TEXT NOT NULL,
    PRIMARY KEY (tenant_id, txn_uid),
    UNIQUE (tenant_id, source_row_digest),
    CHECK((counterparty_resolution='EXACT_VERIFIED') =
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
    fee_mode TEXT NOT NULL CHECK(fee_mode IN
        ('NO_FEE','EMBEDDED_DEBIT','SEPARATE_FEE_ROW')),
    fee_minor INTEGER NOT NULL CHECK(fee_minor >= 0),
    eligibility_basis TEXT NOT NULL CHECK(eligibility_basis IN
        ('RECIPROCAL_ACCOUNT','TRACE_AND_ACCOUNT')),
    binding_digest TEXT NOT NULL,
    candidate_digest TEXT NOT NULL,
    cost_tuple_jcs BLOB NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'EXACT' CHECK(match_type IN
        ('EXACT','FEE_ADJUSTED','PARTIAL','FX')),
    currency_mode TEXT,
    fx_rule_id TEXT,
    fx_receipt_digest TEXT,
    principal_count INTEGER NOT NULL DEFAULT 2 CHECK(principal_count >= 2),
    PRIMARY KEY (tenant_id, run_id, edge_id),
    CHECK(left_txn_uid < right_txn_uid),
    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
);
CREATE TABLE IF NOT EXISTS recon_edge_member (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    txn_uid TEXT NOT NULL,
    member_role TEXT NOT NULL CHECK(member_role IN ('OUTFLOW','INFLOW','FEE')),
    member_ordinal INTEGER NOT NULL CHECK(member_ordinal >= 0),
    PRIMARY KEY (tenant_id, run_id, edge_id, member_role, member_ordinal),
    UNIQUE (tenant_id, run_id, edge_id, txn_uid),
    FOREIGN KEY (tenant_id, run_id, edge_id)
        REFERENCES recon_edge(tenant_id, run_id, edge_id),
    FOREIGN KEY (tenant_id, txn_uid)
        REFERENCES recon_transaction(tenant_id, txn_uid)
);
CREATE TABLE IF NOT EXISTS recon_classification (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    classification_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('FORCED','AMBIGUOUS','UNMATCHED','BLOCKED')),
    affects_reporting INTEGER NOT NULL CHECK(affects_reporting=0),
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
    state TEXT NOT NULL CHECK(state IN ('PENDING','STAGED','BLOCKED')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    PRIMARY KEY (tenant_id, run_id, seq),
    UNIQUE (tenant_id, run_id, path),
    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
);
CREATE TABLE IF NOT EXISTS recon_verification_receipt (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    receipt_digest TEXT NOT NULL,
    nonce TEXT NOT NULL,
    evidence_manifest_digest TEXT NOT NULL,
    verifier_id TEXT NOT NULL,
    signer_key_id TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    signer_revocation_epoch INTEGER NOT NULL CHECK(signer_revocation_epoch >= 0),
    signer_trust_digest TEXT NOT NULL CHECK(length(signer_trust_digest)=64),
    code_closure_digest TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('PASS','BLOCK')),
    verified_at TEXT NOT NULL,
    receipt_jcs BLOB NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (receipt_digest),
    FOREIGN KEY (tenant_id, run_id) REFERENCES recon_run(tenant_id, run_id)
);
CREATE TABLE IF NOT EXISTS recon_review (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    verification_receipt_digest TEXT NOT NULL,
    verifier_id TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('ACCEPT','REJECT','DEFER')),
    actor_id TEXT NOT NULL,
    idempotency_digest TEXT NOT NULL,
    affects_reporting INTEGER NOT NULL CHECK(affects_reporting=0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, review_id),
    UNIQUE (tenant_id, run_id, idempotency_digest),
    FOREIGN KEY (tenant_id, run_id, edge_id)
        REFERENCES recon_edge(tenant_id, run_id, edge_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES recon_verification_receipt(tenant_id, run_id),
    FOREIGN KEY (verification_receipt_digest)
        REFERENCES recon_verification_receipt(receipt_digest)
);
DROP TRIGGER IF EXISTS recon_run_no_illegal_transition;
CREATE TRIGGER recon_run_no_illegal_transition
BEFORE UPDATE OF state ON recon_run
WHEN NOT (
 (OLD.state='QUEUED' AND NEW.state IN ('LEASED','FAILED','CANCELLED')) OR
 (OLD.state='LEASED' AND NEW.state IN ('QUEUED','RUNNING','FAILED','CANCELLED')) OR
 (OLD.state='RUNNING' AND NEW.state IN ('QUEUED','EVIDENCE_STAGED','FAILED','CANCELLED')) OR
 (OLD.state='EVIDENCE_STAGED' AND NEW.state IN ('VERIFYING','BLOCKED','CANCELLED')) OR
 (OLD.state='VERIFYING' AND NEW.state IN ('VERIFIED','BLOCKED','CANCELLED')) OR
 (OLD.state='VERIFIED' AND NEW.state IN ('PUBLISHED','BLOCKED','CANCELLED'))
)
BEGIN SELECT RAISE(ABORT, 'BLOCK_STATE_TRANSITION'); END;
DROP TRIGGER IF EXISTS recon_publish_requires_pass_receipt;
CREATE TRIGGER recon_publish_requires_pass_receipt
BEFORE UPDATE OF state ON recon_run
WHEN NEW.state='PUBLISHED' AND NOT EXISTS (
 SELECT 1 FROM recon_verification_receipt v
 WHERE v.tenant_id=NEW.tenant_id AND v.run_id=NEW.run_id
   AND v.nonce=NEW.nonce AND v.decision='PASS'
   AND length(v.authority_id) >= 3 AND v.signer_revocation_epoch >= 0
   AND length(v.signer_trust_digest)=64
)
BEGIN SELECT RAISE(ABORT, 'BLOCK_UNVERIFIED_ACCESS'); END;
DROP TRIGGER IF EXISTS recon_review_requires_published_receipt;
CREATE TRIGGER recon_review_requires_published_receipt
BEFORE INSERT ON recon_review
WHEN NOT EXISTS (
 SELECT 1 FROM recon_run r JOIN recon_verification_receipt v
   ON v.tenant_id=r.tenant_id AND v.run_id=r.run_id
 WHERE r.tenant_id=NEW.tenant_id AND r.run_id=NEW.run_id
   AND r.state='PUBLISHED' AND v.decision='PASS'
   AND v.nonce=r.nonce AND v.receipt_digest=NEW.verification_receipt_digest
)
BEGIN SELECT RAISE(ABORT, 'BLOCK_UNVERIFIED_ACCESS'); END;
CREATE TRIGGER IF NOT EXISTS recon_run_event_no_update
BEFORE UPDATE ON recon_run_event BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_run_event_no_delete
BEFORE DELETE ON recon_run_event BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_transaction_no_update
BEFORE UPDATE ON recon_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_transaction_no_delete
BEFORE DELETE ON recon_transaction BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_edge_no_update
BEFORE UPDATE ON recon_edge BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_edge_no_delete
BEFORE DELETE ON recon_edge BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_edge_member_no_update
BEFORE UPDATE ON recon_edge_member BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_edge_member_no_delete
BEFORE DELETE ON recon_edge_member BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_review_no_update
BEFORE UPDATE ON recon_review BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_review_no_delete
BEFORE DELETE ON recon_review BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_verification_receipt_no_update
BEFORE UPDATE ON recon_verification_receipt BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
CREATE TRIGGER IF NOT EXISTS recon_verification_receipt_no_delete
BEFORE DELETE ON recon_verification_receipt BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_A4'); END;
"""


def ensure_a4_v32_schema(conn: sqlite3.Connection) -> bool:
    """Install v3.2 without silently trusting legacy verifier receipts."""

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recon_run'"
    ).fetchone()
    sql = str(row[0]) if row is not None and row[0] is not None else ""
    if "EVIDENCE_STAGED" in sql and "idempotency_digest" in sql:
        receipt_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recon_verification_receipt'"
        ).fetchone()
        if receipt_exists is not None:
            columns = {
                str(item[1])
                for item in conn.execute("PRAGMA table_info(recon_verification_receipt)")
            }
            missing = {
                "authority_id",
                "signer_revocation_epoch",
                "signer_trust_digest",
            } - columns
            if missing:
                receipt_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM recon_verification_receipt"
                    ).fetchone()[0]
                )
                if receipt_count:
                    return False
                for statement in (
                    "ALTER TABLE recon_verification_receipt ADD COLUMN authority_id TEXT NOT NULL DEFAULT ''",
                    "ALTER TABLE recon_verification_receipt ADD COLUMN signer_revocation_epoch INTEGER NOT NULL DEFAULT -1",
                    "ALTER TABLE recon_verification_receipt ADD COLUMN signer_trust_digest TEXT NOT NULL DEFAULT ''",
                ):
                    conn.execute(statement)
        edge_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recon_edge'"
        ).fetchone()
        if edge_exists is not None:
            edge_columns = {
                str(item[1]) for item in conn.execute("PRAGMA table_info(recon_edge)")
            }
            migrations = {
                "match_type": "ALTER TABLE recon_edge ADD COLUMN match_type TEXT NOT NULL DEFAULT 'EXACT' CHECK(match_type IN ('EXACT','FEE_ADJUSTED','PARTIAL','FX'))",
                "currency_mode": "ALTER TABLE recon_edge ADD COLUMN currency_mode TEXT",
                "fx_rule_id": "ALTER TABLE recon_edge ADD COLUMN fx_rule_id TEXT",
                "fx_receipt_digest": "ALTER TABLE recon_edge ADD COLUMN fx_receipt_digest TEXT",
                "principal_count": "ALTER TABLE recon_edge ADD COLUMN principal_count INTEGER NOT NULL DEFAULT 2 CHECK(principal_count >= 2)",
            }
            for column, statement in migrations.items():
                if column not in edge_columns:
                    conn.execute(statement)
        transaction_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recon_transaction'"
        ).fetchone()
        if transaction_exists is not None:
            transaction_columns = {
                str(item[1])
                for item in conn.execute("PRAGMA table_info(recon_transaction)")
            }
            transaction_migrations = {
                "value_date": "ALTER TABLE recon_transaction ADD COLUMN value_date TEXT",
                "duplicate_of_reference_token": "ALTER TABLE recon_transaction ADD COLUMN duplicate_of_reference_token TEXT",
                "reversal_of_reference_token": "ALTER TABLE recon_transaction ADD COLUMN reversal_of_reference_token TEXT",
            }
            for column, statement in transaction_migrations.items():
                if column not in transaction_columns:
                    conn.execute(statement)
        conn.executescript(_SCHEMA)
        return True
    legacy_rows = 0
    for table in ("recon_run", "a4_attempt"):
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists is not None:
            legacy_rows += int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    if legacy_rows:
        return False
    conn.executescript(_DROP_LEGACY)
    conn.executescript(_SCHEMA)
    return True
