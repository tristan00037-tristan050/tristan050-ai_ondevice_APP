-- 최근 1시간 창구 요약 뷰(필요 시 MATERIALIZED VIEW + REFRESH JOB 고려)
CREATE OR REPLACE VIEW accounting_os_summary_1h AS
SELECT
  aj.tenant,
  SUM(CASE WHEN aj.action='approvals.approve' THEN 1 ELSE 0 END) AS approvals_approved,
  SUM(CASE WHEN aj.action='approvals.reject'  THEN 1 ELSE 0 END) AS approvals_rejected,
  (SELECT COUNT(*) FROM export_jobs ej WHERE ej.tenant=aj.tenant AND ej.created_at >= NOW() - INTERVAL '1 hour') AS exports_total,
  (SELECT COUNT(*) FROM export_jobs ej WHERE ej.tenant=aj.tenant AND ej.status='failed'  AND ej.created_at >= NOW() - INTERVAL '1 hour') AS exports_failed,
  (SELECT COUNT(*) FROM export_jobs ej WHERE ej.tenant=aj.tenant AND ej.status='expired' AND ej.created_at >= NOW() - INTERVAL '1 hour') AS exports_expired,
  (SELECT COUNT(*) FROM recon_sessions rs WHERE rs.tenant=aj.tenant AND rs.created_at >= NOW() - INTERVAL '1 hour') AS recon_open
FROM accounting_audit_events aj
WHERE aj.ts >= NOW() - INTERVAL '1 hour'
GROUP BY aj.tenant;

