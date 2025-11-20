/**
 * 쿼리 최적화 유틸리티
 * 쿼리 실행 계획 분석 및 최적화 제안
 *
 * @module db/queryOptimization
 */
/**
 * 쿼리 실행 계획 분석
 */
export declare function explainQuery(sql: string, params?: unknown[]): Promise<unknown>;
/**
 * 인덱스 사용 여부 확인
 */
export declare function checkIndexUsage(tableName: string, columnName: string): Promise<boolean>;
/**
 * 테이블 통계 정보 조회
 */
export declare function getTableStats(tableName: string): Promise<{
    rowCount: number;
    tableSize: string;
    indexSize: string;
}>;
/**
 * 느린 쿼리 감지 (PostgreSQL pg_stat_statements 필요)
 */
export declare function getSlowQueries(limit?: number): Promise<Array<{
    query: string;
    calls: number;
    totalTime: number;
    meanTime: number;
}>>;
/**
 * 인덱스 최적화 제안
 */
export declare function suggestIndexes(tableName: string): Promise<Array<{
    column: string;
    reason: string;
}>>;
//# sourceMappingURL=queryOptimization.d.ts.map