/**
 * CS OS Dashboard API 라우트
 * R9-S1: CS 티켓 요약 데이터 제공
 * 
 * @module bff-accounting/routes/cs-os-dashboard
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { summarizeTickets } from '@appcore/service-core-cs';

const router = Router();

/**
 * GET /v1/cs/os/dashboard
 * CS OS Dashboard용 집계 데이터 조회
 */
router.get(
  '/dashboard',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      // 테넌트: 가드에서 설정된 tenantId 사용
      const tenant = req.tenantId || req.headers['x-tenant'] as string || 'default';
      
      // 쿼리 파라미터: windowDays (기본값: 7일)
      const windowDaysParam = req.query.windowDays ? parseInt(req.query.windowDays as string, 10) : undefined;
      const windowDays = windowDaysParam !== undefined ? windowDaysParam : 7;

      // 유효성 검사
      if (windowDays < 1 || windowDays > 365) {
        return res.status(400).json({
          error_code: 'INVALID_WINDOW_DAYS',
          message: 'windowDays must be between 1 and 365',
        });
      }

      // service-core-cs의 summarizeTickets 호출
      const summary = await summarizeTickets({
        tenant,
        windowDays,
      });

      // 응답 형식
      res.json({
        window: {
          days: windowDays,
        },
        summary: {
          total: summary.total,
          byStatus: summary.byStatus,
        },
      });
    } catch (e: any) {
      console.error('[CS OS Dashboard] Error:', e);
      console.error('[CS OS Dashboard] Stack:', e?.stack);
      next(e);
    }
  }
);

export default router;

