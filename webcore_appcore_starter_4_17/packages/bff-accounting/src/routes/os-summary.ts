import { Router } from 'express';
import { pool } from '@appcore/data-pg';

const router = Router();

function requireOps(req: any, res: any, next: any) {
  if (!['operator', 'auditor', 'admin'].includes(req?.ctx?.role)) {
    return res.status(403).json({
      error_code: 'FORBIDDEN',
      request_id: req.ctx?.request_id || req.id,
      message: 'operator/auditor/admin only',
    });
  }
  next();
}

router.get('/v1/accounting/os/summary', requireOps, async (req: any, res: any, next: any) => {
  try {
    const { tenant } = req.ctx;
    // 최근 1시간 창구 요약 (필요시 005 뷰 사용)
    const q = (s: string, a: any[]) => pool.query(s, a);

    const [approvals, exportsSum, recon, errors] = await Promise.all([
      q(
        `SELECT
           SUM(CASE WHEN action='approvals.approve' THEN 1 ELSE 0 END) AS approved,
           SUM(CASE WHEN action='approvals.reject'  THEN 1 ELSE 0 END) AS rejected
         FROM accounting_audit_events
         WHERE tenant=$1 AND ts >= NOW() - INTERVAL '1 hour'`,
        [tenant]
      ),
      q(
        `SELECT
           COUNT(*) AS total,
           SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
           SUM(CASE WHEN status='expired' THEN 1 ELSE 0 END) AS expired
         FROM export_jobs WHERE tenant=$1 AND created_at >= NOW() - INTERVAL '1 hour'`,
        [tenant]
      ),
      q(
        `SELECT
           COUNT(*) AS open
         FROM recon_sessions WHERE tenant=$1 AND created_at >= NOW() - INTERVAL '1 hour'`,
        [tenant]
      ),
      q(
        `SELECT COUNT(*) AS err5xx
         FROM accounting_audit_events
         WHERE tenant=$1 AND ts >= NOW() - INTERVAL '1 hour' AND action='error.5xx'`,
        [tenant]
      ),
    ]);

    res.json({
      approvals: approvals.rows[0] || { approved: 0, rejected: 0 },
      exports: exportsSum.rows[0] || { total: 0, failed: 0, expired: 0 },
      recon: recon.rows[0] || { open: 0 },
      errors: errors.rows[0] || { err5xx: 0 },
      // 레이턴시/레이트리밋 등은 Prometheus 기반 위젯으로 병행 표출
    });
  } catch (e) {
    next(e);
  }
});

export default router;

