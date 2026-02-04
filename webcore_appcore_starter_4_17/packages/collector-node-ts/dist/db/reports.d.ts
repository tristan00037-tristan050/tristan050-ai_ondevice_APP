/**
 * 리포트 데이터베이스 레포지토리
 * 인메모리 저장소를 데이터베이스로 교체
 *
 * @module db/reports
 */
export interface Report {
    id: string;
    tenantId: string;
    report: unknown;
    markdown?: string;
    createdAt: number;
    updatedAt: number;
}
/**
 * 리포트 저장
 */
export declare function saveReport(report: Report): Promise<void>;
/**
 * 리포트 조회
 */
export declare function getReport(id: string, tenantId: string): Promise<Report | null>;
/**
 * 리포트 목록 조회 (서버 측 필터링)
 */
export declare function listReports(tenantId: string, filters: {
    severity?: 'info' | 'warn' | 'block';
    policyVersion?: string;
    since?: number;
}, pagination: {
    page: number;
    limit: number;
}): Promise<{
    reports: Array<{
        id: string;
        createdAt: number;
        updatedAt: number;
        severity?: 'info' | 'warn' | 'block';
        policyVersion?: string;
    }>;
    totalCount: number;
}>;
/**
 * 리포트 삭제 (보존 정책)
 */
export declare function deleteReports(tenantId: string, cutoffTime: number): Promise<number>;
//# sourceMappingURL=reports.d.ts.map