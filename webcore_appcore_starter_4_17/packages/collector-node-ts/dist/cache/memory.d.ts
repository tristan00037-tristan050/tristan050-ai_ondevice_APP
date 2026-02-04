/**
 * 인메모리 캐시 구현
 * Redis가 없는 경우를 위한 간단한 캐시
 * 프로덕션에서는 Redis 사용 권장
 *
 * @module cache/memory
 */
declare class MemoryCache {
    private cache;
    private maxSize;
    constructor(maxSize?: number);
    /**
     * 캐시에 값 저장
     */
    set<T>(key: string, value: T, ttlMs: number): void;
    /**
     * 캐시에서 값 조회
     */
    get<T>(key: string): T | null;
    /**
     * 캐시에서 값 삭제
     */
    delete(key: string): void;
    /**
     * 캐시 초기화
     */
    clear(): void;
    /**
     * 만료된 항목 정리
     */
    cleanup(): number;
    /**
     * 오래된 항목 제거 (LRU 방식)
     */
    private evictOldest;
    /**
     * 캐시 통계
     */
    stats(): {
        size: number;
        maxSize: number;
    };
}
export declare const memoryCache: MemoryCache;
export {};
//# sourceMappingURL=memory.d.ts.map