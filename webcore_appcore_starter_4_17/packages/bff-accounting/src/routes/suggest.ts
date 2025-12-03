/**
 * 분개 추천 라우트
 * POST /v1/accounting/postings/suggest
 * 
 * @module bff-accounting/routes/suggest
 */

import { Router, Request, Response } from 'express';
import Ajv, { type ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';
import { suggestPostings, type SuggestRequest, type SuggestResponse } from '@appcore/service-core-accounting/suggest.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '../../../../..');

// Ajv 인스턴스 생성
const ajv = new (Ajv as any)({
  allErrors: true,
  verbose: true,
  strict: false,  // strict 모드 비활성화 (anyOf 내 required 필드 문제 해결)
  validateFormats: true,
  removeAdditional: false,
});
(addFormats as any)(ajv);

// OpenAPI 스키마 로드 (요청 검증용)
let validateSuggest: ValidateFunction | null = null;
try {
  const openApiPath = path.join(ROOT_DIR, 'contracts/accounting.openapi.yaml');
  // OpenAPI에서 SuggestRequest 스키마 추출하여 Ajv 검증 함수 생성
  // 간단한 검증을 위해 직접 스키마 정의
  const requestSchema = {
    type: 'object',
    required: ['items'],
    properties: {
        items: {
          type: 'array',
          items: {
            type: 'object',
            required: ['amount'],
            properties: {
              desc: { type: 'string' },
              description: { type: 'string' }, // OpenAPI에서 description도 허용
              amount: { type: 'string', pattern: '^-?[0-9]+(\\.[0-9]{1,2})?$' },
              currency: { type: 'string', pattern: '^[A-Z]{3}$' },
            },
            // desc 또는 description 중 하나는 필수
            anyOf: [
              { required: ['desc'] },
              { required: ['description'] }
            ]
          },
        },
      policy_version: { type: 'string' },
    },
  };
  validateSuggest = ajv.compile(requestSchema as any) as ValidateFunction;
} catch (error) {
  console.warn('Failed to load OpenAPI schema for request validation:', error);
}

const router = Router();

/**
 * POST /v1/accounting/postings/suggest
 * 분개 추천 엔드포인트
 */
router.post('/suggest', async (req: Request, res: Response) => {
  try {
    // 1. 인증 확인 (401)
    const apiKey = req.headers['x-api-key'] as string | undefined;
    const tenantId = req.headers['x-tenant'] as string | undefined;
    
    if (!apiKey || !tenantId) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Missing X-Api-Key or X-Tenant header',
      });
    }

    // 2. 권한 확인 (403) - 기본적으로 모든 인증된 사용자 허용
    // TODO: 역할 기반 권한 체크 추가 (operator 이상만 허용)

    // 3. 요청 검증 (Ajv) - 422
    if (validateSuggest) {
      if (!validateSuggest(req.body)) {
        return res.status(422).json({
          error: 'Validation Error',
          details: validateSuggest.errors ?? [],
        });
      }
    }

    // 4. Rate Limit 확인 (429)
    // TODO: Rate limiting 미들웨어 추가
    // if (rateLimitExceeded(tenantId, '/v1/accounting/postings/suggest')) {
    //   return res.status(429).json({
    //     error: 'Too Many Requests',
    //     message: 'Rate limit exceeded',
    //   });
    // }

    // 5. Idempotency-Key 및 client_request_id 처리
    const idempotencyKey = req.headers['idempotency-key'] as string | undefined;
    const clientRequestId = req.body.client_request_id as string | undefined;
    
    // TODO: 멱등성 캐시 확인 (동일한 idempotencyKey/clientRequestId로 이전 요청이 있으면 캐시된 결과 반환)

    // 6. 요청 파싱 (desc 또는 description 필드 지원, currency는 body 또는 item 레벨에서 허용)
    const defaultCurrency = req.body.currency || 'KRW';
    const request: SuggestRequest = {
      items: (req.body.items || req.body.line_items || []).map((item: any) => ({
        desc: item.desc || item.description || '',
        amount: String(item.amount || '0'),
        currency: String(item.currency || defaultCurrency),
      })),
      policy_version: req.body.policy_version,
    };

    // 7. 서비스 코어 호출
    const policyVersion = request.policy_version || 'v1.0.0';
    const response: SuggestResponse = suggestPostings(request, policyVersion);

    // 8. 응답 반환 (200)
    res.status(200).json(response);
  } catch (error) {
    console.error('Error in suggest postings:', error);
    
    // 500 에러 응답
    res.status(500).json({
      error: 'Internal Server Error',
      message: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

export default router;

