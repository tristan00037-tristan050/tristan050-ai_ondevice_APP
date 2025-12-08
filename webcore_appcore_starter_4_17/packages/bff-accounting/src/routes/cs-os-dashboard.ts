/**
 * CS OS Dashboard API 라우트
 * R8-S1: Stub 라우트만 제공
 * 
 * @module bff-accounting/routes/cs-os-dashboard
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { getCsOsDashboardSummary } from '@appcore/service-core-cs';

const router = Router();

/**
 * GET /v1/cs/os/dashboard
 * CS OS Dashboard용 집계 데이터 조회 (Stub)
 */
router.get(
  '/v1/cs/os/dashboard',
  requireTenantAuth,
  requireRole('operator', 'auditor'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      const summary = await getCsOsDashboardSummary(tenant);
      
      res.json({
        ok: true,
        summary,
      });
    } catch (e) {
      next(e);
    }
  }
);

export default router;

