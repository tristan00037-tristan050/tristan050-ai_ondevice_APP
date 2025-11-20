/**
 * PostgreSQL 데이터베이스 클라이언트
 *
 * @module db/client
 */
import pg from 'pg';
declare const pool: pg.Pool;
/**
 * 데이터베이스 쿼리 실행
 */
export declare function query<T extends pg.QueryResultRow = pg.QueryResultRow>(text: string, params?: unknown[]): Promise<pg.QueryResult<T>>;
/**
 * 트랜잭션 실행
 */
export declare function transaction<T>(callback: (client: pg.PoolClient) => Promise<T>): Promise<T>;
/**
 * 데이터베이스 연결 종료
 */
export declare function close(): Promise<void>;
/**
 * 데이터베이스 연결 상태 확인
 */
export declare function healthCheck(): Promise<boolean>;
export default pool;
//# sourceMappingURL=client.d.ts.map