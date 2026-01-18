/**
 * Alerting API
 * Rule-based alerting endpoints
 */

import { Router, Request, Response } from 'express';
import { requireAuth, extractTenantId } from '../../control_plane/auth/middleware';
import { requirePermission } from '../../control_plane/auth/rbac';
import { evaluateAlertRules, getFiredAlerts, createAlertRule } from '../alerting/rules';
import { AlertRule } from '../alerting/rules';

const router = Router();

/**
 * POST /api/v1/telemetry/alerts/evaluate
 * Evaluate alert rules
 */
router.post(
  '/evaluate',
  requireAuth,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const fired = evaluateAlertRules(tenantId);

    res.json({
      fired_count: fired.length,
      alerts: fired,
    });
  }
);

/**
 * GET /api/v1/telemetry/alerts
 * Get fired alerts
 */
router.get(
  '/',
  requireAuth,
  requirePermission('tenant:read'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const filters = {
      rule_id: req.query.rule_id as string | undefined,
      metric_name: req.query.metric_name as string | undefined,
      start_time: req.query.start_time ? new Date(req.query.start_time as string) : undefined,
      end_time: req.query.end_time ? new Date(req.query.end_time as string) : undefined,
    };

    const alerts = getFiredAlerts(tenantId, filters);

    res.json({
      alerts,
      count: alerts.length,
    });
  }
);

/**
 * POST /api/v1/telemetry/alerts/rules
 * Create alert rule
 */
router.post(
  '/rules',
  requireAuth,
  requirePermission('tenant:write'),
  async (req: Request, res: Response) => {
    const tenantId = extractTenantId(req);
    if (!tenantId) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body = req.body as Omit<AlertRule, 'id'>;

    // Fail-Closed: Ensure tenant_id matches
    if (body.tenant_id !== tenantId) {
      return res.status(403).json({
        error: 'Forbidden',
        message: 'Cross-tenant access denied',
      });
    }

    const rule = createAlertRule(body);

    res.status(201).json({ rule });
  }
);

export default router;

