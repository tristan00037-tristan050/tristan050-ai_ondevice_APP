/**
 * 쿼리 최적화 유틸리티
 * 쿼리 실행 계획 분석 및 최적화 제안
 *
 * @module db/queryOptimization
 */
import { query } from './client.js';
/**
 * 쿼리 실행 계획 분석
 */
export async function explainQuery(sql, params) {
    const explainSql = `EXPLAIN ANALYZE ${sql}`;
    const result = await query(explainSql, params);
    return result.rows;
}
/**
 * 인덱스 사용 여부 확인
 */
export async function checkIndexUsage(tableName, columnName) {
    const result = await query(`SELECT indexname, indexdef
     FROM pg_indexes
     WHERE tablename = $1 AND indexdef LIKE $2`, [tableName, `%${columnName}%`]);
    return result.rows.length > 0;
}
/**
 * 테이블 통계 정보 조회
 */
export async function getTableStats(tableName) {
    const result = await query(`SELECT 
       pg_class.reltuples::bigint AS row_count,
       pg_size_pretty(pg_total_relation_size(pg_class.oid)) AS table_size,
       pg_size_pretty(pg_indexes_size(pg_class.oid)) AS index_size
     FROM pg_class
     WHERE relname = $1`, [tableName]);
    if (result.rows.length === 0) {
        throw new Error(`Table ${tableName} not found`);
    }
    return {
        rowCount: parseInt(result.rows[0].row_count, 10),
        tableSize: result.rows[0].table_size,
        indexSize: result.rows[0].index_size,
    };
}
/**
 * 느린 쿼리 감지 (PostgreSQL pg_stat_statements 필요)
 */
export async function getSlowQueries(limit = 10) {
    try {
        const result = await query(`SELECT 
         query,
         calls,
         total_exec_time AS total_time,
         mean_exec_time AS mean_time
       FROM pg_stat_statements
       ORDER BY mean_exec_time DESC
       LIMIT $1`, [limit]);
        return result.rows.map((row) => {
            const r = row;
            return {
                query: r.query,
                calls: r.calls,
                totalTime: r.total_time,
                meanTime: r.mean_time,
            };
        });
    }
    catch (error) {
        // pg_stat_statements가 활성화되지 않은 경우
        console.warn('pg_stat_statements not available:', error);
        return [];
    }
}
/**
 * 인덱스 최적화 제안
 */
export async function suggestIndexes(tableName) {
    const suggestions = [];
    // WHERE 절에서 자주 사용되는 컬럼 확인
    // 실제로는 pg_stat_statements나 쿼리 로그를 분석해야 함
    // 여기서는 기본적인 제안만 제공
    // reports 테이블의 경우
    if (tableName === 'reports') {
        // tenant_id는 이미 인덱스가 있지만, 복합 인덱스 확인
        const hasCompositeIndex = await checkIndexUsage('reports', 'tenant_id, created_at');
        if (!hasCompositeIndex) {
            suggestions.push({
                column: 'tenant_id, created_at',
                reason: 'Frequently used together in WHERE and ORDER BY clauses',
            });
        }
    }
    return suggestions;
}
//# sourceMappingURL=queryOptimization.js.map