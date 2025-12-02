#!/usr/bin/env node

/**
 * 만료 데이터 정리 스크립트
 * RETENTION_DAYS 환경 변수로 보관 기간 설정
 */

import pg from 'pg';

const { Pool } = pg;

const RETENTION_DAYS = Number(process.env.RETENTION_DAYS ?? 30);
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

async function run() {
  const client = await pool.connect();
  try {
    console.log(`🧹 cleanup: retention=${RETENTION_DAYS}d`);
    await client.query(`UPDATE export_jobs SET status='expired'
                        WHERE status IN ('pending','running','done')
                          AND created_at < NOW() - INTERVAL '${RETENTION_DAYS} days'`);
    await client.query(`DELETE FROM recon_sessions
                        WHERE created_at < NOW() - INTERVAL '${RETENTION_DAYS} days'`);
    console.log('✅ cleanup done');
  } finally {
    client.release();
    await pool.end();
  }
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});

