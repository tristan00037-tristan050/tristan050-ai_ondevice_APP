/**
 * 알림 시스템
 * 에러 알림, 성능 저하 알림, 용량 임계값 알림
 *
 * @module utils/notifications
 */
interface Notification {
    level: 'info' | 'warning' | 'error' | 'critical';
    title: string;
    message: string;
    timestamp: number;
    metadata?: Record<string, unknown>;
}
/**
 * 알림 전송
 */
export declare function sendNotification(notification: Notification): Promise<void>;
/**
 * 에러 알림
 */
export declare function notifyError(title: string, message: string, metadata?: Record<string, unknown>): Promise<void>;
/**
 * 성능 저하 알림
 */
export declare function notifyPerformanceDegradation(metric: string, threshold: number, currentValue: number): Promise<void>;
/**
 * 용량 임계값 알림
 */
export declare function notifyCapacityThreshold(resource: string, usage: number, threshold: number): Promise<void>;
/**
 * 데이터베이스 연결 실패 알림
 */
export declare function notifyDatabaseConnectionFailure(error: Error): Promise<void>;
/**
 * Rate Limit 초과 알림
 */
export declare function notifyRateLimitExceeded(tenantId: string, endpoint: string, limit: number): Promise<void>;
export {};
//# sourceMappingURL=notifications.d.ts.map