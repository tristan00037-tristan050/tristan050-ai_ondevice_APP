import { Router } from 'express';
import { pool, getRiskScore } from '@appcore/data-pg';
import { requireTenantAuth, requireRole as requireRoleGuard } from '../shared/guards.js';

const router = Router();

function requireAuditRole(req: any, res: any, next: any) {
  const role = req?.ctx?.role || (req.headers['x-user-role'] as string);
  if (!['auditor', 'admin'].includes(role)) {
    return res.status(403).json({
      error_code: 'FORBIDDEN',
      request_id: req.ctx?.request_id || req.id,
      message: 'auditor/admin only',
    });
  }
  next();
}

router.get('/v1/accounting/audit', requireTenantAuth, requireAuditRole, async (req: any, res: any, next: any) => {
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
  requireTenantAuth,
  requireRoleGuard('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      const { subject_type, subject_id, reason, reason_code, amount, currency, is_high_value } = req.body || {};
      
      // 1. Audit 이벤트 기록
      const { auditLog } = await import('@appcore/service-core-accounting');
      await auditLog({
        tenant,
        request_id: req.ctx?.request_id || req.id,
        actor: req.ctx?.actor || '',
        action: 'manual_review_request',
        subject_type,
        subject_id,
        payload: { 
          reason, 
          client_request_id: req.header('Idempotency-Key') || undefined,
          ...(reason_code !== undefined && { reason_code }),
          ...(amount !== undefined && { amount }),
          ...(currency !== undefined && { currency }),
          ...(is_high_value !== undefined && { is_high_value }),
        },
      });
      
      // 2. Manual Review Queue에 추가 (Risk 정보 기반)
      try {
        // posting_id로 RiskScore 조회
        const riskScore = await getRiskScore(tenant, subject_id);
        
        if (riskScore) {
          // Risk + ManualReview 연결 규칙
          const reasons = [...riskScore.reasons];
          if (reason_code) {
            reasons.push(reason_code);
          }
          
          const { enqueueManualReview } = await import('@appcore/data-pg');
          await enqueueManualReview({
            tenant,
            posting_id: subject_id,
            risk_level: riskScore.level,
            reasons: [...new Set(reasons)], // 중복 제거
            source: 'HUD',
          });
        }
      } catch (queueError) {
        // Queue 추가 실패해도 audit 이벤트는 기록되었으므로 경고만
        console.warn('Failed to enqueue manual review:', queueError);
      }
      
      res.status(201).json({ ok: true });
    } catch (e) {
      next(e);
    }
  }
);

export default router;

