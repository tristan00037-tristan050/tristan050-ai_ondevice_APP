-- accounting_audit_events: 승인/대사/내보내기 등 모든 중요 이벤트 감사용
CREATE TABLE IF NOT EXISTS accounting_audit_events (
  id           BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tenant       TEXT        NOT NULL,
  request_id   TEXT,
  idem_key     TEXT,
  actor        TEXT,
  ip           INET,
  route        TEXT,
  action       TEXT        NOT NULL,          -- ex) approval_apply, export_create, recon_match
  subject_type TEXT,                          -- ex) report, export_job, recon_session
  subject_id   TEXT,
  payload      JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON accounting_audit_events (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON accounting_audit_events (action, ts DESC);

