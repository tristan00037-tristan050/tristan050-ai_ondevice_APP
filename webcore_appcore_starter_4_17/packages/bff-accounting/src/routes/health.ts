/**
 * Health Check & Ready Check 엔드포인트
 * 
 * @module bff-accounting/routes/health
 */

import { Router } from 'express';
import { pool } from '@appcore/data-pg';

const router = Router();

/**
 * GET /healthz
 * 단순 alive 체크
 */
router.get('/healthz', (req: any, res: any) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

/**
 * GET /readyz
 * DB 연결 및 마이그레이션 상태 체크
 */
router.get('/readyz', async (req: any, res: any) => {
  try {
    // 1. DB 연결 체크
    const dbCheck = await pool.query('SELECT 1 as health');
    if (dbCheck.rows.length === 0) {
      return res.status(503).json({
        status: 'unhealthy',
        reason: 'database_connection_failed',
        timestamp: new Date().toISOString(),
      });
    }
    
    // 2. 기본 테이블 존재 확인
    const tableCheck = await pool.query(`
      SELECT COUNT(*) as count 
      FROM accounting_audit_events 
      LIMIT 1
    `);
    
    // 3. 마이그레이션 버전 확인 (선택)
    let migrationVersion = 'unknown';
    try {
      const migrationCheck = await pool.query(`
        SELECT version 
        FROM schema_migrations 
        ORDER BY version DESC 
        LIMIT 1
      `);
      if (migrationCheck.rows.length > 0) {
        migrationVersion = migrationCheck.rows[0].version;
      }
    } catch {
      // schema_migrations 테이블이 없어도 계속 진행
    }
    
    res.json({
      status: 'ready',
      database: 'connected',
      migration_version: migrationVersion,
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(503).json({
      status: 'unhealthy',
      reason: 'database_error',
      error: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

export default router;

