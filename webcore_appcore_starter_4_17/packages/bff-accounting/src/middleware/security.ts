/**
 * 보안 헤더 및 레이트 리밋 미들웨어
 * 
 * @module bff-accounting/middleware/security
 */

import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import type { RequestHandler } from 'express';

export const securityHeaders: RequestHandler = helmet({
  crossOriginResourcePolicy: { policy: 'same-site' },
  contentSecurityPolicy: false, // BFF API이므로 비활성
});

export const limitGeneral = rateLimit({
  windowMs: 60_000,
  max: 300, // 1분 300요청
  standardHeaders: true,
  legacyHeaders: false,
});

export const limitApprovals = rateLimit({
  windowMs: 60_000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
});

export const limitExports = rateLimit({
  windowMs: 60_000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
});

export const limitRecon = rateLimit({
  windowMs: 60_000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
});

