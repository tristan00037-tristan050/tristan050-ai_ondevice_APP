/**
 * 배치 처리 유틸리티
 * 대량 리포트 인제스트 및 타임라인 집계 최적화
 *
 * @module db/batch
 */
import { transaction } from './client.js';
/**
 * 배치 리포트 저장 (트랜잭션 사용)
 */
export async function batchSaveReports(reports) {
    await transaction(async (client) => {
        for (const report of reports) {
            await client.query(`INSERT INTO reports (id, tenant_id, report_data, markdown, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6)
         ON CONFLICT (id) DO UPDATE SET
           report_data = $3,
           markdown = $4,
           updated_at = $6`, [
                report.id,
                report.tenantId,
                JSON.stringify(report.report),
                report.markdown || null,
                report.createdAt,
                report.updatedAt,
            ]);
        }
    });
}
/**
 * 배치 리포트 삭제 (보존 정책)
 */
export async function batchDeleteReports(tenantId, cutoffTime, batchSize = 1000) {
    let totalDeleted = 0;
    while (true) {
        const result = await transaction(async (client) => {
            const deleteResult = await client.query(`DELETE FROM reports
         WHERE id IN (
           SELECT id FROM reports
           WHERE tenant_id = $1 AND created_at < $2
           LIMIT $3
         )`, [tenantId, cutoffTime, batchSize]);
            return deleteResult.rowCount || 0;
        });
        totalDeleted += result;
        if (result < batchSize) {
            break; // 더 이상 삭제할 항목이 없음
        }
    }
    return totalDeleted;
}
/**
 * 타임라인 집계 배치 처리
 * 시간 버킷별로 그룹화하여 집계
 */
export async function batchAggregateTimeline(tenantId, startTime, endTime, bucketSizeMs = 3600000 // 1시간
) {
    const { query } = await import('./client.js');
    // SQL을 사용한 직접 집계 (더 효율적)
    const result = await query(`SELECT 
       (FLOOR(created_at / $3) * $3) AS bucket_time,
       COUNT(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM jsonb_array_elements(report_data->'policy'->'evaluations') AS eval
         WHERE eval->>'severity' = 'info'
       )) AS info_count,
       COUNT(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM jsonb_array_elements(report_data->'policy'->'evaluations') AS eval
         WHERE eval->>'severity' = 'warn'
       )) AS warn_count,
       COUNT(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM jsonb_array_elements(report_data->'policy'->'evaluations') AS eval
         WHERE eval->>'severity' = 'block'
       )) AS block_count
     FROM reports
     WHERE tenant_id = $1 AND created_at >= $2 AND created_at < $4
     GROUP BY bucket_time
     ORDER BY bucket_time`, [tenantId, startTime, bucketSizeMs, endTime]);
    return result.rows.map((row) => ({
        time: row.bucket_time,
        info: parseInt(row.info_count, 10),
        warn: parseInt(row.warn_count, 10),
        block: parseInt(row.block_count, 10),
    }));
}
//# sourceMappingURL=batch.js.map