/**
 * Manual Review API 라우트
 * 
 * @module bff-accounting/routes/manual-review
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { 
  listManualReview, 
  getManualReview, 
  updateManualReviewStatus,
  enqueueManualReview,
  type ManualReviewStatus 
} from '@appcore/data-pg';
import { getRiskScore } from '@appcore/data-pg';

const router = Router();

/**
 * GET /v1/accounting/manual-review
 * Manual Review 목록 조회
 */
router.get(
  '/v1/accounting/manual-review',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      
      // 상태 필터 검증 (PENDING, IN_REVIEW, APPROVED, REJECTED만 허용)
      const statusParam = req.query.status as string | undefined;
      let status: ManualReviewStatus | undefined;
      if (statusParam) {
        if (!['PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED'].includes(statusParam)) {
          return res.status(400).json({
            error_code: 'INVALID_STATUS',
            message: 'status must be one of: PENDING, IN_REVIEW, APPROVED, REJECTED',
          });
        }
        status = statusParam as ManualReviewStatus;
      }
      
      // 페이지네이션 파라미터
      const page = parseInt(req.query.page as string || '1', 10);
      const pageSize = parseInt(req.query.page_size as string || req.query.limit as string || '50', 10);
      const offset = parseInt(req.query.offset as string || String((page - 1) * pageSize), 10);
      const limit = pageSize;
      
      // limit + 1로 조회하여 다음 페이지 존재 여부 확인
      const allItems = await listManualReview({
        tenant,
        status,
        limit: limit + 1,
        offset,
      });
      
      const hasMore = allItems.length > limit;
      const items = hasMore ? allItems.slice(0, limit) : allItems;
      
      res.json({
        items,
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

/**
 * GET /v1/accounting/manual-review/:id
 * Manual Review 상세 조회
 */
router.get(
  '/v1/accounting/manual-review/:id',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      const id = parseInt(req.params.id, 10);
      
      const item = await getManualReview(tenant, id);
      
      if (!item) {
        return res.status(404).json({
          error_code: 'NOT_FOUND',
          message: `Manual review item not found: id=${id}`,
        });
      }
      
      res.json(item);
    } catch (e) {
      next(e);
    }
  }
);

/**
 * POST /v1/accounting/manual-review/:id/resolve
 * Manual Review 상태 변경 (승인/거절)
 */
router.post(
  '/v1/accounting/manual-review/:id/resolve',
  requireTenantAuth,
  requireRole('auditor'),
  async (req: any, res: any, next: any) => {
    try {
      const tenant = req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      const id = parseInt(req.params.id, 10);
      const { status, note } = req.body;
      
      if (!status || !['APPROVED', 'REJECTED'].includes(status)) {
        return res.status(400).json({
          error_code: 'INVALID_REQUEST',
          message: 'status must be APPROVED or REJECTED',
        });
      }
      
      const userId = req.ctx?.actor || req.headers['x-user-id'] as string || undefined;
      
      const updated = await updateManualReviewStatus({
        tenant,
        id,
        status: status as ManualReviewStatus,
        assignee: userId,
        note,
      });
      
      res.json(updated);
    } catch (e: any) {
      if (e.message?.includes('not found')) {
        return res.status(404).json({
          error_code: 'NOT_FOUND',
          message: e.message,
        });
      }
      next(e);
    }
  }
);

export default router;

