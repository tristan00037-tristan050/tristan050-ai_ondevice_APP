/**
 * Rate Limiting 미들웨어
 * 테넌트별, IP별, 토큰별 요청 제한
 *
 * @module mw/rateLimit
 */
import { Request, Response, NextFunction } from 'express';
interface RateLimitConfig {
    windowMs: number;
    maxRequests: number;
}
/**
 * Rate Limiting 미들웨어 생성
 */
export declare function createRateLimiter(config: RateLimitConfig): (req: Request, res: Response, next: NextFunction) => void;
/**
 * 기본 Rate Limiter (100 requests per minute)
 */
export declare const defaultRateLimiter: (req: Request, res: Response, next: NextFunction) => void;
/**
 * 엄격한 Rate Limiter (10 requests per minute)
 */
export declare const strictRateLimiter: (req: Request, res: Response, next: NextFunction) => void;
/**
 * 느슨한 Rate Limiter (1000 requests per minute)
 */
export declare const looseRateLimiter: (req: Request, res: Response, next: NextFunction) => void;
export {};
//# sourceMappingURL=rateLimit.d.ts.map