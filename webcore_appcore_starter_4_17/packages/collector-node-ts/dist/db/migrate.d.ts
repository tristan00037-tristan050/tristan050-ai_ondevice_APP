/**
 * 데이터베이스 마이그레이션 스크립트
 * 스키마 초기화 및 인메모리 데이터 마이그레이션
 *
 * @module db/migrate
 */
/**
 * 스키마 초기화
 */
export declare function initSchema(): Promise<void>;
/**
 * 인메모리 데이터 마이그레이션 (레거시 지원)
 * 기존 Map 기반 저장소에서 데이터베이스로 마이그레이션
 */
export declare function migrateFromMemory(reports: Map<string, {
    id: string;
    tenantId: string;
    report: unknown;
    markdown?: string;
    createdAt: number;
    updatedAt: number;
}>, signHistory: Array<{
    reportId: string;
    tenantId: string;
    requestedBy: string;
    token: string;
    issuedAt: number;
    expiresAt: number;
    createdAt: number;
}>, signTokenCache: Map<string, {
    token: string;
    expiresAt: number;
}>): Promise<void>;
//# sourceMappingURL=migrate.d.ts.map