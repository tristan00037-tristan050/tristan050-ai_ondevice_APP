/**
 * 에러 핸들러 미들웨어
 * 구조화된 에러 응답 제공
 * 
 * @module bff-accounting/middleware/errorHandler
 */

import type { Request, Response, NextFunction } from 'express';

type AnyError = Error & { status?: number; code?: string; details?: unknown };

export function errorHandler(err: AnyError, req: Request, res: Response, _next: NextFunction) {
  const status = err.status && Number.isInteger(err.status) ? Number(err.status) : 500;
  const payload = {
    error_code: err.code ?? (status >= 500 ? 'internal_error' : 'request_error'),
    message: err.message ?? 'unexpected error',
    request_id: (req as any).requestId ?? '',
    details: err.details ?? null,
  };
  res.status(status).json(payload);
}

