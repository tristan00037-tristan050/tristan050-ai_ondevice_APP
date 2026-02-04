/**
 * 서명 토큰 캐시 데이터베이스 레포지토리
 * 멱등성 보장을 위한 토큰 캐시
 *
 * @module db/signTokenCache
 */
export interface SignTokenCache {
    cacheKey: string;
    token: string;
    expiresAt: number;
    createdAt: number;
}
/**
 * 토큰 캐시 조회
 */
export declare function getTokenCache(cacheKey: string): Promise<{
    token: string;
    expiresAt: number;
} | null>;
/**
 * 토큰 캐시 저장
 */
export declare function setTokenCache(cache: SignTokenCache): Promise<void>;
/**
 * 만료된 토큰 정리
 */
export declare function cleanupExpiredTokens(): Promise<number>;
//# sourceMappingURL=signTokenCache.d.ts.map