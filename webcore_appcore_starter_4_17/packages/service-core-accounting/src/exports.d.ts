/**
 * Export 잡 관리
 *
 * @module service-core-accounting/exports
 */
export type ExportFilters = {
    since?: string;
    until?: string;
    severity?: string[];
    limitDays?: number;
};
export interface ExportJob {
    jobId: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    filters: ExportFilters;
    created_at: string;
    completed_at?: string;
    file_url?: string;
}
/**
 * Export 잡 생성
 *
 * @param tenant - 테넌트 ID
 * @param filters - 필터 조건
 * @returns Export 잡 정보
 */
export declare function createExportJob(tenant: string, filters: ExportFilters): Promise<ExportJob>;
/**
 * Export 잡 상태 조회
 *
 * @param jobId - 잡 ID
 * @returns Export 잡 정보
 */
export declare function getExportJob(jobId: string): Promise<ExportJob>;
//# sourceMappingURL=exports.d.ts.map