/**
 * 배치 처리 유틸리티
 * 대량 리포트 인제스트 및 타임라인 집계 최적화
 *
 * @module db/batch
 */
import type { Report } from './reports.js';
/**
 * 배치 리포트 저장 (트랜잭션 사용)
 */
export declare function batchSaveReports(reports: Report[]): Promise<void>;
/**
 * 배치 리포트 삭제 (보존 정책)
 */
export declare function batchDeleteReports(tenantId: string, cutoffTime: number, batchSize?: number): Promise<number>;
/**
 * 타임라인 집계 배치 처리
 * 시간 버킷별로 그룹화하여 집계
 */
export declare function batchAggregateTimeline(tenantId: string, startTime: number, endTime: number, bucketSizeMs?: number): Promise<Array<{
    time: number;
    info: number;
    warn: number;
    block: number;
}>>;
//# sourceMappingURL=batch.d.ts.map