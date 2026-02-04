/**
 * 요청 ID 미들웨어
 * X-Request-Id 헤더가 없으면 자동 생성
 * 
 * @module bff-accounting/middleware/requestId
 */

import { randomUUID } from 'node:crypto';
import type { Request, Response, NextFunction } from 'express';

export function requestId(req: Request, res: Response, next: NextFunction) {
  const id = req.header('X-Request-Id') || randomUUID();
  (req as any).requestId = id;
  res.setHeader('X-Request-Id', id);
  next();
}


