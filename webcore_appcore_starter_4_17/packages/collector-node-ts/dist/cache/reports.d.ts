/**
 * 리포트 캐싱 전략
 * 리포트 목록 및 타임라인 집계 결과 캐싱
 *
 * @module cache/reports
 */
interface ReportsListCacheKey {
    tenantId: string;
    severity?: string;
    policyVersion?: string;
    since?: number;
    page: number;
    limit: number;
}
interface TimelineCacheKey {
    tenantId: string;
    windowH: number;
}
/**
 * 리포트 목록 캐시 조회
 */
export declare function getCachedReportsList(key: ReportsListCacheKey): {
    reports: Array<{
        id: string;
        createdAt: number;
        updatedAt: number;
        severity?: 'info' | 'warn' | 'block';
        policyVersion?: string;
    }>;
    totalCount: number;
    etag: string;
} | null;
/**
 * 리포트 목록 캐시 저장
 */
export declare function setCachedReportsList(key: ReportsListCacheKey, data: {
    reports: Array<{
        id: string;
        createdAt: number;
        updatedAt: number;
        severity?: 'info' | 'warn' | 'block';
        policyVersion?: string;
    }>;
    totalCount: number;
    etag: string;
}, ttlMs?: number): void;
/**
 * 리포트 목록 캐시 무효화
 */
export declare function invalidateReportsListCache(tenantId: string): void;
/**
 * 타임라인 캐시 조회
 */
export declare function getCachedTimeline(key: TimelineCacheKey): {
    window_h: number;
    buckets: Array<{
        time: number;
        info: number;
        warn: number;
        block: number;
    }>;
} | null;
/**
 * 타임라인 캐시 저장
 */
export declare function setCachedTimeline(key: TimelineCacheKey, data: {
    window_h: number;
    buckets: Array<{
        time: number;
        info: number;
        warn: number;
        block: number;
    }>;
}, ttlMs?: number): void;
/**
 * 타임라인 캐시 무효화
 */
export declare function invalidateTimelineCache(tenantId: string): void;
/**
 * 리포트 저장 시 관련 캐시 무효화
 */
export declare function invalidateOnReportSave(tenantId: string): void;
export {};
//# sourceMappingURL=reports.d.ts.map