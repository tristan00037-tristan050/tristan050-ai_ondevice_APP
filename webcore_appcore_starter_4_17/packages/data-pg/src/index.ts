/**
 * PostgreSQL 데이터 계층
 * 
 * @module data-pg
 */

import { Pool } from 'pg';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Pool을 lazy initialization으로 변경 (DATABASE_URL 로드 시점 문제 해결)
let _pool: Pool | null = null;

function getPool(): Pool {
  if (!_pool) {
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) {
      throw new Error('DATABASE_URL environment variable is not set');
    }
    if (typeof databaseUrl !== 'string') {
      console.error('[data-pg] DATABASE_URL must be a string, got:', typeof databaseUrl);
      throw new Error('DATABASE_URL must be a string');
    }
    _pool = new Pool({
      connectionString: databaseUrl,
    });
  }
  return _pool;
}

export const pool = new Proxy({} as Pool, {
  get(_target, prop) {
    return getPool()[prop as keyof Pool];
  },
});

export async function ping(): Promise<boolean> {
  const { Pool } = await import('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  try {
    await pool.query('SELECT 1');
    return true;
  } finally {
    await pool.end();
  }
}

export * from './repos/auditRepo.js';
export * from './repos/externalLedgerRepo.js';
export * from './repos/exportsRepo.js';
export * from './repos/reconRepo.js';
export * from './repos/riskRepo.js';
export * from './repos/manualReviewRepo.js';

export async function exec(sql: string, params?: any[]) {
  return pool.query(sql, params);
}

export async function migrateDir(dir = path.join(__dirname, '../migrations')) {
  // 마이그레이션 실행 시 별도 Pool 생성 (DATABASE_URL 확인)
  if (!process.env.DATABASE_URL) {
    throw new Error('DATABASE_URL environment variable is not set');
  }
  
  const migratePool = new Pool({
    connectionString: process.env.DATABASE_URL,
  });
  
  try {
    const files = fs.readdirSync(dir)
      .filter(f => /^\d+_.*\.sql$/.test(f))
      .sort();
    
    for (const f of files) {
      const sql = fs.readFileSync(path.join(dir, f), 'utf8');
      await migratePool.query(sql);
      console.log(`✅ Applied migration: ${f}`);
    }
  } finally {
    await migratePool.end();
  }
}

export type ExportJobRow = {
  job_id: string;
  tenant: string;
  status: string;
  created_at: string;
  exp: number;
  sha256: string;
  manifest: any;
  filters: any;
  idem_key: string | null;
};

export type ReconSessionRow = {
  session_id: string;
  tenant: string;
  created_at: string;
  matches: any;
  unmatched_bank: any;
  unmatched_ledger: any;
  idem_key: string | null;
};


