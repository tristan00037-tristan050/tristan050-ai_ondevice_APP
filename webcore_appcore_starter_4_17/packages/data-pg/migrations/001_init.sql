-- Export Jobs 테이블
CREATE TABLE IF NOT EXISTS export_jobs (
  job_id      TEXT PRIMARY KEY,
  tenant      TEXT NOT NULL,
  status      TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL,
  exp         BIGINT NOT NULL,
  sha256      TEXT NOT NULL,
  manifest    JSONB NOT NULL,
  filters     JSONB NOT NULL,
  idem_key    TEXT
);

CREATE INDEX IF NOT EXISTS export_jobs_tenant_idx ON export_jobs(tenant);
CREATE UNIQUE INDEX IF NOT EXISTS export_jobs_tenant_idem_uq ON export_jobs(tenant, idem_key) WHERE idem_key IS NOT NULL;

-- Reconciliation Sessions 테이블
CREATE TABLE IF NOT EXISTS recon_sessions (
  session_id       TEXT PRIMARY KEY,
  tenant           TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL,
  matches          JSONB NOT NULL,
  unmatched_bank   JSONB NOT NULL,
  unmatched_ledger JSONB NOT NULL,
  idem_key         TEXT
);

CREATE INDEX IF NOT EXISTS recon_sessions_tenant_idx ON recon_sessions(tenant);
CREATE UNIQUE INDEX IF NOT EXISTS recon_sessions_tenant_idem_uq ON recon_sessions(tenant, idem_key) WHERE idem_key IS NOT NULL;


