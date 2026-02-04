/**
 * Rate Limiting 미들웨어
 * 테넌트별, IP별, 토큰별 요청 제한
 *
 * @module mw/rateLimit
 */
// 인메모리 Rate Limit 저장소 (프로덕션에서는 Redis 사용 권장)
class RateLimitStore {
    store = new Map();
    cleanupInterval = null;
    constructor() {
        // 주기적으로 만료된 항목 정리 (1분마다)
        this.cleanupInterval = setInterval(() => {
            this.cleanup();
        }, 60000);
    }
    /**
     * 요청 카운트 증가
     */
    increment(key, windowMs) {
        const now = Date.now();
        const entry = this.store.get(key);
        if (!entry || entry.resetAt < now) {
            // 새 윈도우 시작
            const newEntry = {
                count: 1,
                resetAt: now + windowMs,
            };
            this.store.set(key, newEntry);
            return {
                count: 1,
                resetAt: newEntry.resetAt,
                remaining: 0, // maxRequests는 미들웨어에서 계산
            };
        }
        // 기존 윈도우에서 카운트 증가
        entry.count++;
        this.store.set(key, entry);
        return {
            count: entry.count,
            resetAt: entry.resetAt,
            remaining: 0, // maxRequests는 미들웨어에서 계산
        };
    }
    /**
     * 만료된 항목 정리
     */
    cleanup() {
        const now = Date.now();
        for (const [key, entry] of this.store.entries()) {
            if (entry.resetAt < now) {
                this.store.delete(key);
            }
        }
    }
    /**
     * 저장소 초기화
     */
    destroy() {
        if (this.cleanupInterval) {
            clearInterval(this.cleanupInterval);
        }
        this.store.clear();
    }
}
const rateLimitStore = new RateLimitStore();
/**
 * Rate Limit 키 생성
 */
function getRateLimitKey(req, type) {
    switch (type) {
        case 'tenant':
            return `ratelimit:tenant:${req.tenantId || 'unknown'}`;
        case 'ip':
            return `ratelimit:ip:${req.ip || req.socket.remoteAddress || 'unknown'}`;
        case 'token':
            // API Key를 기반으로 한 토큰 식별자
            const apiKey = req.headers['x-api-key'];
            return `ratelimit:token:${apiKey || 'unknown'}`;
        default:
            return 'ratelimit:unknown';
    }
}
/**
 * Rate Limiting 미들웨어 생성
 */
export function createRateLimiter(config) {
    return (req, res, next) => {
        // Rate Limit 키 생성 (테넌트 우선, 없으면 IP)
        const key = req.tenantId
            ? getRateLimitKey(req, 'tenant')
            : getRateLimitKey(req, 'ip');
        const { count, resetAt } = rateLimitStore.increment(key, config.windowMs);
        // Rate Limit 헤더 설정
        res.set({
            'X-RateLimit-Limit': config.maxRequests.toString(),
            'X-RateLimit-Remaining': Math.max(0, config.maxRequests - count).toString(),
            'X-RateLimit-Reset': Math.ceil(resetAt / 1000).toString(),
        });
        // Rate Limit 초과 확인
        if (count > config.maxRequests) {
            // Rate Limit 초과 알림 (비동기, 블로킹하지 않음)
            import('../utils/notifications.js').then(({ notifyRateLimitExceeded }) => {
                notifyRateLimitExceeded(req.tenantId || 'unknown', req.path, config.maxRequests).catch(console.error);
            }).catch(() => {
                // 알림 실패는 무시
            });
            res.status(429).json({
                error: 'Too Many Requests',
                message: `Rate limit exceeded. Maximum ${config.maxRequests} requests per ${config.windowMs / 1000} seconds.`,
                retryAfter: Math.ceil((resetAt - Date.now()) / 1000),
            });
            return;
        }
        next();
    };
}
/**
 * 기본 Rate Limiter (100 requests per minute)
 */
export const defaultRateLimiter = createRateLimiter({
    windowMs: 60000, // 1분
    maxRequests: 100,
});
/**
 * 엄격한 Rate Limiter (10 requests per minute)
 */
export const strictRateLimiter = createRateLimiter({
    windowMs: 60000, // 1분
    maxRequests: 10,
});
/**
 * 느슨한 Rate Limiter (1000 requests per minute)
 */
export const looseRateLimiter = createRateLimiter({
    windowMs: 60000, // 1분
    maxRequests: 1000,
});
//# sourceMappingURL=rateLimit.js.map