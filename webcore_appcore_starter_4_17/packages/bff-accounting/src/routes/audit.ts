import { Router } from 'express';
import { pool } from '@appcore/data-pg';

const router = Router();

function requireAuditRole(req: any, res: any, next: any) {
  if (!['auditor', 'admin'].includes(req?.ctx?.role)) {
    return res.status(403).json({
      error_code: 'FORBIDDEN',
      request_id: req.ctx?.request_id || req.id,
      message: 'auditor/admin only',
    });
  }
  next();
}

function requireRole(...roles: string[]) {
  return (req: any, res: any, next: any) => {
    if (!roles.includes(req?.ctx?.role)) {
      return res.status(403).json({
        error_code: 'FORBIDDEN',
        request_id: req.ctx?.request_id || req.id,
        message: `${roles.join('/')} only`,
      });
    }
    next();
  };
}

router.get('/v1/accounting/audit', requireAuditRole, async (req: any, res: any, next: any) => {
  try {
    const { tenant } = req.ctx;
    const { actor, action, from, to, page = '1', page_size = '50' } = req.query;
    const p = Math.max(1, parseInt(String(page), 10));
    const ps = Math.min(200, Math.max(1, parseInt(String(page_size), 10)));

    const args: any[] = [tenant];
    const where = ['tenant = $1'];
    if (actor) {
      args.push(actor);
      where.push(`actor = $${args.length}`);
    }
    if (action) {
      args.push(action);
      where.push(`action = $${args.length}`);
    }
    if (from) {
      args.push(from);
      where.push(`ts >= $${args.length}`);
    }
    if (to) {
      args.push(to);
      where.push(`ts <= $${args.length}`);
    }

    const offset = (p - 1) * ps;
    const sql = `
      SELECT id, ts, action, subject_type, subject_id, actor, request_id
      FROM accounting_audit_events
      WHERE ${where.join(' AND ')}
      ORDER BY ts DESC
      LIMIT ${ps} OFFSET ${offset};
    `;
    const countSql = `SELECT COUNT(*) AS total FROM accounting_audit_events WHERE ${where.join(' AND ')}`;

    const [list, cnt] = await Promise.all([
      pool.query(sql, args),
      pool.query(countSql, args),
    ]);

    res.json({
      total: Number(cnt.rows[0].total),
      page: p,
      page_size: ps,
      items: list.rows,
    });
  } catch (e) {
    next(e);
  }
});

// POST /v1/accounting/audit/manual-review
router.post(
  '/v1/accounting/audit/manual-review',
  requireRole('operator', 'auditor', 'admin'),
  async (req: any, res: any, next: any) => {
    try {
      const { subject_type, subject_id, reason } = req.body || {};
      const { auditLog } = await import('@appcore/service-core-accounting');
      await auditLog({
        tenant: req.ctx?.tenant || 'default',
        request_id: req.ctx?.request_id || req.id,
        actor: req.ctx?.actor || '',
        action: 'manual_review_request',
        subject_type,
        subject_id,
        payload: { reason, client_request_id: req.header('Idempotency-Key') || undefined },
      });
      res.status(201).json({ ok: true });
    } catch (e) {
      next(e);
    }
  }
);

export default router;

