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

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
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

export async function exec(sql: string, params?: any[]) {
  return pool.query(sql, params);
}

export async function migrateDir(dir = path.join(__dirname, '../migrations')) {
  const files = fs.readdirSync(dir)
    .filter(f => /^\d+_.*\.sql$/.test(f))
    .sort();
  
  for (const f of files) {
    const sql = fs.readFileSync(path.join(dir, f), 'utf8');
    await exec(sql);
    console.log(`✅ Applied migration: ${f}`);
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


