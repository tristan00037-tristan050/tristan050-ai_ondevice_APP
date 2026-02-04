/**
 * PostgreSQL 데이터베이스 클라이언트
 *
 * @module db/client
 */
import pg from 'pg';
const { Pool } = pg;
// 환경 변수에서 데이터베이스 연결 정보 읽기
const pool = new Pool({
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '5432'),
    database: process.env.DB_NAME || 'collector',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD || 'postgres',
    max: 20, // 최대 연결 수
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
});
// 연결 풀 이벤트 리스너
pool.on('error', (err) => {
    console.error('Unexpected error on idle client', err);
    process.exit(-1);
});
/**
 * 데이터베이스 쿼리 실행
 */
export async function query(text, params) {
    const start = Date.now();
    try {
        const res = await pool.query(text, params);
        const duration = Date.now() - start;
        console.log('Executed query', { text, duration, rows: res.rowCount });
        return res;
    }
    catch (error) {
        console.error('Query error', { text, error });
        throw error;
    }
}
/**
 * 트랜잭션 실행
 */
export async function transaction(callback) {
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        const result = await callback(client);
        await client.query('COMMIT');
        return result;
    }
    catch (error) {
        await client.query('ROLLBACK');
        throw error;
    }
    finally {
        client.release();
    }
}
/**
 * 데이터베이스 연결 종료
 */
export async function close() {
    await pool.end();
}
/**
 * 데이터베이스 연결 상태 확인
 */
export async function healthCheck() {
    try {
        const result = await pool.query('SELECT 1');
        return result.rowCount === 1;
    }
    catch (error) {
        console.error('Database health check failed', error);
        return false;
    }
}
export default pool;
//# sourceMappingURL=client.js.map