/**
 * OS LLM Usage API 라우트
 * R10-S1: LLM 사용 감사(Audit) 이벤트 수집
 * 
 * @module bff-accounting/routes/os-llm-usage
 */

import { Router } from 'express';
import { requireTenantAuth } from '../shared/guards.js';

const router = Router();

/**
 * POST /v1/os/llm-usage
 * LLM 사용 이벤트 수집
 * 
 * R10-S1: 로그만 기록 (R10-S2 이후 PG 테이블 적재/리포트로 확장 가능)
 * 
 * Playbook 규칙: 원문 텍스트는 받지 않는다.
 */
router.post('/v1/os/llm-usage', requireTenantAuth, async (req, res, next) => {
  try {
    // reqContext 미들웨어에서 설정된 컨텍스트 사용
    const tenantId = (req as any).tenantId || req.body.tenantId;
    const userId = req.headers['x-user-id'] as string || req.body.userId;
    const userRole = req.headers['x-user-role'] as string || 'operator';
    
    const body = req.body as {
      domain: string;
      engineId: string;
      engineVariant?: string;
      engineMode: string;
      engineStub?: boolean;
      outcome: string;
      feature: string;
      timestamp: string;
      suggestionLength: number;
    };

    // 원문 텍스트는 받지 않는다. (Playbook 규칙)
    // suggestionLength만 허용하고, 실제 텍스트 필드는 무시

    // R10-S1: 로그만 기록
    // R10-S2 이후: PG 테이블 적재 또는 이벤트 스트림 전송
    const logEvent = {
      type: 'llm_usage',
      tenant: tenantId || body.tenantId,
      userId: userId || body.userId,
      userRole: userRole || 'unknown',
      domain: body.domain,
      engineId: body.engineId,
      engineVariant: body.engineVariant,
      engineMode: body.engineMode,
      engineStub: body.engineStub,
      feature: body.feature,
      suggestionLength: body.suggestionLength,
      outcome: body.outcome,
      timestamp: body.timestamp || new Date().toISOString(),
      ts: new Date().toISOString(),
    };

    console.log(JSON.stringify(logEvent));

    // 204 No Content 응답 (성공적으로 수신했지만 응답 본문 없음)
    res.status(204).end();
  } catch (err) {
    next(err);
  }
});

export default router;

