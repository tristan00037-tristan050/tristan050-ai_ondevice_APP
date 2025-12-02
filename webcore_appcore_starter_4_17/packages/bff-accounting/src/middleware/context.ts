/**
 * 요청 컨텍스트 미들웨어
 * tenant, actor, ip, request_id를 req.ctx에 주입
 * 
 * @module bff-accounting/middleware/context
 */

import type { Request, Response, NextFunction } from 'express';

export function reqContext() {
  return function (req: Request, res: Response, next: NextFunction) {
    const xff = (req.headers['x-forwarded-for'] as string | undefined)?.split(',')[0]?.trim();
    (req as any).ctx = {
      tenant: req.get('X-Tenant') ?? 'default',
      actor: (req.get('X-Api-Key') ?? '').split(':')[0] || 'unknown',
      ip: xff || req.socket.remoteAddress || '',
      request_id: (req as any).requestId || req.get('X-Request-Id') || String(res.getHeader('X-Request-Id') || ''),
    };
    next();
  };
}

