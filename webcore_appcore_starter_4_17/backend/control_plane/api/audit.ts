/**
 * Audit Logs API
 * Immutable append-only audit log queries
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../auth/middleware';
import { requirePermission } from '../auth/rbac';
import { queryAuditLogs } from '../audit/service';
import { AuditAction, AuditResourceType } from '../models/audit';

const router = Router();

/**
 * GET /api/v1/audit/logs
 * Query audit logs (tenant-scoped, read-only)
 */
router.get(
  '/',
  requireAuth,
  requirePermission('audit:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    // Parse query parameters
    const filters = {
      user_id: req.query.user_id as string | undefined,
      action: req.query.action as AuditAction | undefined,
      resource_type: req.query.resource_type as AuditResourceType | undefined,
      resource_id: req.query.resource_id as string | undefined,
      start_date: req.query.start_date ? new Date(req.query.start_date as string) : undefined,
      end_date: req.query.end_date ? new Date(req.query.end_date as string) : undefined,
    };

    // Fail-Closed: Cross-tenant access blocked by queryAuditLogs
    const logs = queryAuditLogs(tenantId, filters);
    res.json({ logs, count: logs.length });
  }
);

export default router;

