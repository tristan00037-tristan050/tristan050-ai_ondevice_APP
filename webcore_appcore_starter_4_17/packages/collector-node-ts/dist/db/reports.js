/**
 * 리포트 데이터베이스 레포지토리
 * 인메모리 저장소를 데이터베이스로 교체
 *
 * @module db/reports
 */
import { query } from './client.js';
/**
 * 리포트 저장
 */
export async function saveReport(report) {
    await query(`INSERT INTO reports (id, tenant_id, report_data, markdown, created_at, updated_at)
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
/**
 * 리포트 조회
 */
export async function getReport(id, tenantId) {
    const result = await query(`SELECT id, tenant_id, report_data, markdown, created_at, updated_at
     FROM reports
     WHERE id = $1 AND tenant_id = $2`, [id, tenantId]);
    if (result.rows.length === 0) {
        return null;
    }
    const row = result.rows[0];
    return {
        id: row.id,
        tenantId: row.tenant_id,
        report: row.report_data,
        markdown: row.markdown || undefined,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
    };
}
/**
 * 리포트 목록 조회 (서버 측 필터링)
 */
export async function listReports(tenantId, filters, pagination) {
    // WHERE 조건 구성
    const conditions = ['tenant_id = $1'];
    const params = [tenantId];
    let paramIndex = 2;
    // severity 필터 (JSONB 쿼리)
    if (filters.severity) {
        conditions.push(`EXISTS (
        SELECT 1 FROM jsonb_array_elements(report_data->'policy'->'evaluations') AS eval
        WHERE eval->>'severity' = $${paramIndex}
      )`);
        params.push(filters.severity);
        paramIndex++;
    }
    // policy_version 필터
    if (filters.policyVersion) {
        conditions.push(`report_data->'policy'->>'policy_version' ILIKE $${paramIndex}`);
        params.push(`%${filters.policyVersion}%`);
        paramIndex++;
    }
    // since 필터
    if (filters.since) {
        conditions.push(`created_at >= $${paramIndex}`);
        params.push(filters.since);
        paramIndex++;
    }
    const whereClause = conditions.join(' AND ');
    // 전체 개수 조회
    const countResult = await query(`SELECT COUNT(*) as count FROM reports WHERE ${whereClause}`, params);
    const totalCount = parseInt(countResult.rows[0].count, 10);
    // 페이지네이션 적용
    const offset = (pagination.page - 1) * pagination.limit;
    params.push(pagination.limit, offset);
    paramIndex += 2;
    // 리포트 목록 조회
    const result = await query(`SELECT id, created_at, updated_at, report_data
     FROM reports
     WHERE ${whereClause}
     ORDER BY created_at DESC, id ASC
     LIMIT $${paramIndex - 1} OFFSET $${paramIndex}`, params);
    // severity 및 policy_version 추출
    const reports = result.rows.map((row) => {
        const reportData = row.report_data;
        // severity 추출 (가장 높은 severity)
        let maxSeverity;
        if (reportData?.policy?.evaluations) {
            const severities = reportData.policy.evaluations
                .map((e) => e.severity)
                .filter((s) => s === 'info' || s === 'warn' || s === 'block');
            if (severities.includes('block'))
                maxSeverity = 'block';
            else if (severities.includes('warn'))
                maxSeverity = 'warn';
            else if (severities.includes('info'))
                maxSeverity = 'info';
        }
        // policy_version 추출
        const policyVersion = reportData?.policy?.policy_version;
        return {
            id: row.id,
            createdAt: row.created_at,
            updatedAt: row.updated_at,
            severity: maxSeverity,
            policyVersion,
        };
    });
    return { reports, totalCount };
}
/**
 * 리포트 삭제 (보존 정책)
 */
export async function deleteReports(tenantId, cutoffTime) {
    const result = await query(`DELETE FROM reports
     WHERE tenant_id = $1 AND created_at < $2`, [tenantId, cutoffTime]);
    return result.rowCount || 0;
}
//# sourceMappingURL=reports.js.map