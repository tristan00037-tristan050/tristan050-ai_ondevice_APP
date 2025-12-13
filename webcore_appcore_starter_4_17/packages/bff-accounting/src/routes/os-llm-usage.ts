/**
 * OS LLM Usage 라우트
 * R10-S1: LLM Usage Audit v0
 * R10-S2: eventType 필드 처리
 * 
 * @module bff-accounting/routes/os-llm-usage
 */

import { Router } from 'express';
import { requireTenantAuth } from '../shared/guards.js';

export const osLlmUsageRouter = Router();

/**
 * POST /v1/os/llm-usage
 * LLM Usage 이벤트 수집
 * 
 * 텍스트 원문은 받지 않고, 엔진 메타/모드/도메인/이벤트 타입 등만 수집
 */
osLlmUsageRouter.post(
  '/v1/os/llm-usage',
  requireTenantAuth,
  async (req, res, next) => {
    try {
      const tenantId = (req as any).tenantId || req.body.tenantId;
      const userId = req.headers['x-user-id'] as string || req.body.userId;
      const userRole = req.headers['x-user-role'] as string || 'operator';
      const body = req.body as {
        domain: string;
        engineId: string;
        engineVariant?: string;
        engineMode: string;
        engineStub?: boolean;
        eventType: string;  // R10-S2: 추가
        feature: string;
        timestamp: string;
        suggestionLength: number;
      };

      const logEvent = {
        type: 'llm_usage',
        tenant: tenantId,
        userId,
        userRole,
        ...body,
        ts: new Date().toISOString(),
      };

      console.log(JSON.stringify(logEvent));
      res.status(204).end();
    } catch (err) {
      next(err);
    }
  },
);

export default osLlmUsageRouter;

