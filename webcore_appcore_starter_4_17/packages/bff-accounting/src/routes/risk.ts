/**
 * Risk API 라우트
 * 
 * @module bff-accounting/routes/risk
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { getRiskScore, listHighRisk } from '@appcore/data-pg';

const router = Router();

/**
 * GET /v1/accounting/risk/:posting_id
 * 특정 posting의 리스크 점수 조회
 */
router.get(
  '/v1/accounting/risk/:posting_id',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const { posting_id } = req.params;
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      
      const riskScore = await getRiskScore(tenant, posting_id);
      
      if (!riskScore) {
        return res.status(404).json({
          error_code: 'RISK_NOT_FOUND',
          message: 'Risk score not found for given posting_id',
        });
      }
      
      res.json(riskScore);
    } catch (e) {
      next(e);
    }
  }
);

/**
 * GET /v1/accounting/risk/high
 * 최근 HIGH 레벨 거래 목록 조회
 */
router.get(
  '/v1/accounting/risk/high',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      
      // 페이지네이션 파라미터 (page 기반 또는 offset 기반)
      const page = parseInt(req.query.page as string || '1', 10);
      const pageSize = parseInt(req.query.page_size as string || req.query.limit as string || '50', 10);
      const offset = parseInt(req.query.offset as string || String((page - 1) * pageSize), 10);
      const limit = pageSize;
      
      // limit + 1로 조회하여 다음 페이지 존재 여부 확인
      const highRiskList = await listHighRisk(tenant, limit + 1, offset);
      const hasMore = highRiskList.length > limit;
      const items = hasMore ? highRiskList.slice(0, limit) : highRiskList;
      
      // 응답 형식: posting_id, amount, created_at, reasons 요약
      // 실제 amount는 posting에서 가져와야 하지만, 지금은 risk_scores만 반환
      res.json({
        items: items.map(risk => ({
          posting_id: risk.posting_id,
          level: risk.level,
          score: risk.score,
          reasons: risk.reasons,
          created_at: risk.created_at,
        })),
        pagination: {
          page,
          page_size: pageSize,
          offset,
          has_more: hasMore,
          next_page: hasMore ? page + 1 : null,
        },
      });
    } catch (e) {
      next(e);
    }
  }
);

export default router;

