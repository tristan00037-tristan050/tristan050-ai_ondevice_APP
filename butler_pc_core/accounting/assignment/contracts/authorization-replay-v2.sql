CREATE TABLE IF NOT EXISTS accounting_authorization_replay_v2 (
    replay_key TEXT PRIMARY KEY NOT NULL
        CHECK(length(replay_key) = 64 AND replay_key NOT GLOB '*[^0-9a-f]*'),
    jti_hash TEXT NOT NULL
        CHECK(length(jti_hash) = 64 AND jti_hash NOT GLOB '*[^0-9a-f]*'),
    nonce_hash TEXT NOT NULL
        CHECK(length(nonce_hash) = 64 AND nonce_hash NOT GLOB '*[^0-9a-f]*'),
    tenant_id_hash TEXT NOT NULL
        CHECK(length(tenant_id_hash) = 64 AND tenant_id_hash NOT GLOB '*[^0-9a-f]*'),
    session_id_hash TEXT NOT NULL
        CHECK(length(session_id_hash) = 64 AND session_id_hash NOT GLOB '*[^0-9a-f]*'),
    action TEXT NOT NULL CHECK(action IN (
        'ASSIGNMENT_CREATE',
        'RULE_FUTURE_CREATE',
        'RULE_DEACTIVATE',
        'RULE_APPLICATION_REVERT',
        'QUARANTINE_ROW_RECOMPILE',
        'CONFLICT_RESOLVE'
    )),
    resource_hash TEXT NOT NULL
        CHECK(length(resource_hash) = 64 AND resource_hash NOT GLOB '*[^0-9a-f]*'),
    policy_digest TEXT NOT NULL
        CHECK(length(policy_digest) = 64 AND policy_digest NOT GLOB '*[^0-9a-f]*'),
    expires_at INTEGER NOT NULL CHECK(expires_at > 0),
    consumed_at INTEGER NOT NULL CHECK(consumed_at > 0),
    UNIQUE(jti_hash, nonce_hash, tenant_id_hash, session_id_hash)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_accounting_authorization_replay_v2_expiry
ON accounting_authorization_replay_v2(expires_at);
