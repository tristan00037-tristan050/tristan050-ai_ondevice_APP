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
/**
 * 감사 로그 저장
 */
export declare function saveAuditLog(log: AuditLog): void;
/**
 * 감사 로그 미들웨어
 */
export declare function auditMiddleware(req: Request, res: Response, next: NextFunction): void;
/**
 * 보안 이벤트 로깅
 */
export declare function logSecurityEvent(req: Request, eventType: 'rate_limit' | 'unauthorized' | 'forbidden' | 'invalid_input' | 'suspicious_activity', details: string): void;
/**
 * 감사 로그 조회 (관리자용)
 */
export declare function getAuditLogs(filters?: {
    tenantId?: string;
    startTime?: number;
    endTime?: number;
    securityEvent?: boolean;
}, limit?: number): AuditLog[];
//# sourceMappingURL=audit.d.ts.map