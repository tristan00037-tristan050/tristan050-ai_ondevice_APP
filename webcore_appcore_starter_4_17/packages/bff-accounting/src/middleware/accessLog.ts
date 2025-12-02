/**
 * 구조화 액세스 로그 미들웨어
 * JSON 형식으로 요청/응답 로깅
 * 
 * @module bff-accounting/middleware/accessLog
 */

import type { Request, Response, NextFunction } from 'express';
import { redactPII } from './redact.js';

export function accessLog(req: Request, res: Response, next: NextFunction) {
  const start = Date.now();
  const id = (req as any).requestId;

  res.on('finish', () => {
    const ms = Date.now() - start;
    const line = JSON.stringify({
      t: new Date().toISOString(),
      id,
      m: req.method,
      p: redactPII(req.originalUrl || req.url),
      s: res.statusCode,
      ms,
      tenant: req.get('X-Tenant') ?? '',
      idem: req.get('Idempotency-Key') ?? '',
    });
    console.log(line);
  });

  next();
}


