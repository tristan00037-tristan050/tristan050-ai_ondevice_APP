/**
 * 서명 이력 데이터베이스 레포지토리
 *
 * @module db/signHistory
 */
import { query } from './client.js';
/**
 * 서명 이력 저장
 */
export async function saveSignHistory(history) {
    await query(`INSERT INTO sign_history (report_id, tenant_id, requested_by, token, issued_at, expires_at, created_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`, [
        history.reportId,
        history.tenantId,
        history.requestedBy,
        history.token,
        history.issuedAt,
        history.expiresAt,
        history.createdAt,
    ]);
    // 최대 1000개 유지 (오래된 것 삭제)
    await query(`DELETE FROM sign_history
     WHERE id NOT IN (
       SELECT id FROM sign_history
       WHERE report_id = $1 AND tenant_id = $2
       ORDER BY created_at DESC
       LIMIT 1000
     )`, [history.reportId, history.tenantId]);
}
/**
 * 서명 이력 조회
 */
export async function getSignHistory(reportId, tenantId) {
    const result = await query(`SELECT requested_by, issued_at, expires_at, created_at, token
     FROM sign_history
     WHERE report_id = $1 AND tenant_id = $2
     ORDER BY created_at DESC`, [reportId, tenantId]);
    return result.rows.map((row) => ({
        requestedBy: row.requested_by,
        issuedAt: row.issued_at,
        expiresAt: row.expires_at,
        createdAt: row.created_at,
        tokenPreview: row.token.substring(0, 16) + '...',
    }));
}
//# sourceMappingURL=signHistory.js.map