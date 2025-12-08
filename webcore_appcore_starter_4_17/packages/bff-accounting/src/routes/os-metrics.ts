/**
 * OS 메트릭 라우트
 * GET /v1/accounting/os/metrics/pilot - 파일럿 지표
 * 
 * @module bff-accounting/routes/os-metrics
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';

const router = Router();

/**
 * GET /v1/accounting/os/metrics/pilot
 * 파일럿 지표 조회
 * 
 * 현재는 샘플 값 반환 (sample: true)
 * R8에서 report_pilot_metrics.mjs 로직을 service-core-accounting + data-pg repo로 분리하여 실제 집계 구현 예정
 */
router.get(
  '/v1/accounting/os/metrics/pilot',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      // TODO: R8에서 실제 집계 로직 구현
      // 1. report_pilot_metrics.mjs의 쿼리 로직을 service-core-accounting로 이동
      // 2. data-pg repo에 집계 함수 추가
      // 3. 여기서는 service-core-accounting 함수 호출
      
      // 현재는 샘플 값 반환
      const window = {
        from: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
        to: new Date().toISOString(),
      };

      res.json({
        top1_accuracy: 0.67,  // 67%
        top5_accuracy: 1.0,  // 100%
        manual_review_ratio: 0.5,  // 50%
        window,
        sample: true,  // 샘플 데이터 플래그
      });
    } catch (e) {
      next(e);
    }
  }
);

export default router;

