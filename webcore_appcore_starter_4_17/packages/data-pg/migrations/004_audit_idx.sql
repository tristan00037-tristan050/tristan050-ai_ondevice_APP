-- 감사 조회/정렬 가속
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON accounting_audit_events(tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_actor_ts ON accounting_audit_events(tenant, actor, ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_action_ts ON accounting_audit_events(tenant, action, ts DESC);

