/**
 * Express 타입 확장
 * Request 객체에 tenantId, reportId 추가
 */

import { Request } from 'express';

declare global {
  namespace Express {
    interface Request {
      tenantId?: string;
      reportId?: string;
    }
  }
}


