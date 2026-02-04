/**
 * 감사 로그 미들웨어
 * 모든 API 요청 로깅 및 보안 이벤트 감지
 * 
 * @module mw/audit
 */

import { Request, Response, NextFunction } from 'express';

export interface AuditLog {
  timestamp: number;
  method: string;
  path: string;
  tenantId?: string;
  ip: string;
  userAgent?: string;
  statusCode: number;
  responseTime: number;
  error?: string;
  securityEvent?: {
    type: 'rate_limit' | 'unauthorized' | 'forbidden' | 'invalid_input' | 'suspicious_activity';
    details: string;
  };
}

// 감사 로그 저장소 (실제로는 데이터베이스나 로그 집계 시스템에 저장)
const auditLogs: AuditLog[] = [];
const MAX_AUDIT_LOGS = 10000; // 최대 보관 로그 수

/**
 * 감사 로그 저장
 */
export function saveAuditLog(log: AuditLog): void {
  auditLogs.push(log);

  // 최대 개수 초과 시 오래된 로그 제거
  if (auditLogs.length > MAX_AUDIT_LOGS) {
    auditLogs.shift();
  }

  // 실제로는 여기서 로그 집계 시스템(ELK, CloudWatch 등)에 전송
  console.log('[AUDIT]', JSON.stringify(log));
}

/**
 * 감사 로그 미들웨어
 */
export function auditMiddleware(req: Request, res: Response, next: NextFunction): void {
  const startTime = Date.now();
  const ip = req.ip || req.socket.remoteAddress || 'unknown';
  const userAgent = req.headers['user-agent'];

  // 응답 완료 시 감사 로그 저장
  res.on('finish', () => {
    const responseTime = Date.now() - startTime;
    const log: AuditLog = {
      timestamp: Date.now(),
      method: req.method,
      path: req.path,
      tenantId: (req as Request & { tenantId?: string }).tenantId,
      ip,
      userAgent,
      statusCode: res.statusCode,
      responseTime,
    };

    // 보안 이벤트 감지
    if (res.statusCode === 429) {
      log.securityEvent = {
        type: 'rate_limit',
        details: 'Rate limit exceeded',
      };
    } else if (res.statusCode === 401) {
      log.securityEvent = {
        type: 'unauthorized',
        details: 'Unauthorized access attempt',
      };
    } else if (res.statusCode === 403) {
      log.securityEvent = {
        type: 'forbidden',
        details: 'Forbidden access attempt',
      };
    } else if (res.statusCode === 400) {
      log.securityEvent = {
        type: 'invalid_input',
        details: 'Invalid input detected',
      };
    }

    saveAuditLog(log);
  });

  next();
}

/**
 * 보안 이벤트 로깅
 */
export function logSecurityEvent(
  req: Request,
  eventType: 'rate_limit' | 'unauthorized' | 'forbidden' | 'invalid_input' | 'suspicious_activity',
  details: string
): void {
  const ip = req.ip || req.socket.remoteAddress || 'unknown';
  const log: AuditLog = {
    timestamp: Date.now(),
    method: req.method,
    path: req.path,
    tenantId: (req as Request & { tenantId?: string }).tenantId,
    ip,
    userAgent: req.headers['user-agent'],
    statusCode: 0, // 보안 이벤트는 별도 로깅
    responseTime: 0,
    securityEvent: {
      type: eventType,
      details,
    },
  };

  saveAuditLog(log);
}

/**
 * 감사 로그 조회 (관리자용)
 */
export function getAuditLogs(
  filters?: {
    tenantId?: string;
    startTime?: number;
    endTime?: number;
    securityEvent?: boolean;
  },
  limit: number = 100
): AuditLog[] {
  let filtered = auditLogs;

  if (filters?.tenantId) {
    filtered = filtered.filter(log => log.tenantId === filters.tenantId);
  }

  if (filters?.startTime) {
    filtered = filtered.filter(log => log.timestamp >= filters.startTime!);
  }

  if (filters?.endTime) {
    filtered = filtered.filter(log => log.timestamp <= filters.endTime!);
  }

  if (filters?.securityEvent) {
    filtered = filtered.filter(log => log.securityEvent !== undefined);
  }

  return filtered.slice(-limit).reverse(); // 최신순
}

