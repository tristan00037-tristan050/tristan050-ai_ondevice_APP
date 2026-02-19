/**
 * OS LLM Gateway 라우트
 * R10-S2: Remote LLM Gateway 설계
 * 
 * HUD가 외부 LLM을 직접 호출하지 않고, OS Gateway를 통해 나가는 레일 확보
 * 
 * @module bff-accounting/routes/os-llm-gateway
 */

import type { Request, Response, NextFunction } from 'express';
import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import type {
  LlmGatewayRequestBody,
  LlmGatewayResponseBody,
} from './os-llm-gateway.types.js';

// ASSIST_COMPUTE_DEFAULT_OFF_LOCK_V1
import fs from 'fs';
import path from 'path';

const ASSIST_POLICY_PATH = 'docs/ops/contracts/ASSIST_COMPUTE_POLICY_V1.md';

function readAssistPolicy(): string | null {
  try {
    const abs = path.resolve(process.cwd(), ASSIST_POLICY_PATH);
    return fs.readFileSync(abs, 'utf8');
  } catch {
    // fail-closed: policy unreadable => feature stays OFF
    return null;
  }
}

type AssistReqLike = { headers?: Record<string, unknown> };

function isAssistEnabled(req: AssistReqLike): boolean {
  const enabled = String(process.env.ASSIST_COMPUTE_ENABLED || '') === '1';
  if (!enabled) return false;

  const txt = readAssistPolicy();
  if (!txt) return false; // fail-closed: no exception, stay OFF

  if (!txt.includes('ASSIST_COMPUTE_POLICY_V1_TOKEN=1')) return false;
  if (!txt.includes('DEFAULT_OFF=1')) return false;

  const requireHeader = txt.includes('REQUIRE_HEADER=1');
  if (requireHeader) {
    const v = String(req?.headers?.['x-assist-compute'] || '');
    if (v !== '1') return false;
  }
  return true;
}

const router = Router();

/**
 * Gateway 레벨 LLM 출력 정리
 * R10-S2: 서버단 PII 필터 / 정책 필터 자리 마련
 * 
 * @param output - 원본 출력 텍스트
 * @returns 정리된 출력 텍스트
 */
function sanitizeLlmGatewayOutput(output: string): string {
  if (!output) return output;
  let out = output.replace(/\r\n/g, '\n').trim();

  // TODO: 서버단 민감 정보/금지 표현 필터 자리
  // out = maskSensitiveServerSide(out);

  return out;
}

/**
 * POST /v1/os/llm-gateway/completions
 * Remote LLM Gateway 프록시
 * 
 * 현재는 501 Not Implemented + Stub 응답 반환
 * 실제 LLM 호출은 R10-S3 이후 구현 예정
 */
router.post(
  '/v1/os/llm-gateway/completions',
  requireTenantAuth,
  requireRole('operator'),
  async (req: Request<unknown, unknown, LlmGatewayRequestBody>, res: Response, next: NextFunction) => {
    try {
      // ASSIST_COMPUTE_DEFAULT_OFF_GUARD_V1
      if (!isAssistEnabled(req)) {
        return res.status(501).json({ message: 'Assist compute is default OFF (policy-gated).' });
      }
      const tenant = (req as any).tenantId || req.headers['x-tenant'] as string;
      const userId = req.headers['x-user-id'] as string;
      const role = req.headers['x-user-role'] as string;

      if (!tenant || !userId || !role) {
        return res.status(400).json({
          error_code: 'MISSING_OS_HEADERS',
          message: 'X-Tenant, X-User-Id, X-User-Role are required',
        });
      }

      const { domain, taskType, engineId, engineVariant, prompt } = req.body ?? {};

      if (!domain || !taskType || !engineId || !prompt) {
        return res.status(400).json({
          error_code: 'INVALID_LLM_GATEWAY_REQUEST',
          message: 'domain, taskType, engineId, prompt are required',
        });
      }

      // ⚠️ 여기서 아직 외부 LLM 호출은 하지 않는다.
      // R10-S2 스코프: "계약/가드/Stub 응답"까지만.
      const now = new Date().toISOString();

      // R10-S2: Gateway 레벨 후처리 적용
      const rawOutput = `[remote-llm-stub] domain=${domain}, taskType=${taskType}\n\n${prompt}`;
      const sanitizedOutput = sanitizeLlmGatewayOutput(rawOutput);

      const stub: LlmGatewayResponseBody = {
        id: `stub-${Date.now()}`,
        engineId,
        engineVariant,
        createdAt: now,
        output: sanitizedOutput,
        usage: {
          promptTokens: undefined,
          completionTokens: undefined,
          totalTokens: undefined,
        },
        traceId: req.body?.traceId,
      };

      // TODO: 여기에서 LLM Usage v0/v1와 연결할지 여부는 이후 티켓에서 결정
      return res.status(501).json({
        error_code: 'REMOTE_LLM_NOT_IMPLEMENTED',
        message: 'Remote LLM gateway is defined but not implemented yet (design-only stub).',
        stub,
      });
    } catch (e) {
      console.error('[os-llm-gateway] error:', e);
      next(e);
    }
  }
);

export default router;

