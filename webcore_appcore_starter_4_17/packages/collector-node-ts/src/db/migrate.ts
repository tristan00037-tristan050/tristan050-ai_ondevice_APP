/**
 * 데이터베이스 마이그레이션 스크립트
 * 스키마 초기화 및 인메모리 데이터 마이그레이션
 * 
 * @module db/migrate
 */

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { query, transaction } from './client.js';
import type { PoolClient } from 'pg';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * 스키마 초기화
 */
export async function initSchema(): Promise<void> {
  const schemaPath = join(__dirname, 'schema.sql');
  const schema = readFileSync(schemaPath, 'utf-8');
  
  // SQL 문을 세미콜론으로 분리하고 실행
  const statements = schema
    .split(';')
    .map(s => s.trim())
    .filter(s => s.length > 0 && !s.startsWith('--'));

  await transaction(async (client: PoolClient) => {
    for (const statement of statements) {
      if (statement.length > 0) {
        await client.query(statement);
      }
    }
  });

  console.log('✅ Database schema initialized');
}

/**
 * 인메모리 데이터 마이그레이션 (레거시 지원)
 * 기존 Map 기반 저장소에서 데이터베이스로 마이그레이션
 */
export async function migrateFromMemory(
  reports: Map<string, { id: string; tenantId: string; report: unknown; markdown?: string; createdAt: number; updatedAt: number }>,
  signHistory: Array<{ reportId: string; tenantId: string; requestedBy: string; token: string; issuedAt: number; expiresAt: number; createdAt: number }>,
  signTokenCache: Map<string, { token: string; expiresAt: number }>
): Promise<void> {
  console.log('🔄 Migrating in-memory data to database...');

  // 리포트 마이그레이션
  let reportCount = 0;
  for (const report of reports.values()) {
    await query(
      `INSERT INTO reports (id, tenant_id, report_data, markdown, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (id) DO NOTHING`,
      [
        report.id,
        report.tenantId,
        JSON.stringify(report.report),
        report.markdown || null,
        report.createdAt,
        report.updatedAt,
      ]
    );
    reportCount++;
  }
  console.log(`  ✅ Migrated ${reportCount} reports`);

  // 서명 이력 마이그레이션
  let historyCount = 0;
  for (const history of signHistory) {
    await query(
      `INSERT INTO sign_history (report_id, tenant_id, requested_by, token, issued_at, expires_at, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       ON CONFLICT DO NOTHING`,
      [
        history.reportId,
        history.tenantId,
        history.requestedBy,
        history.token,
        history.issuedAt,
        history.expiresAt,
        history.createdAt,
      ]
    );
    historyCount++;
  }
  console.log(`  ✅ Migrated ${historyCount} sign history entries`);

  // 서명 토큰 캐시 마이그레이션
  let cacheCount = 0;
  for (const [cacheKey, cache] of signTokenCache.entries()) {
    // 만료된 토큰은 마이그레이션하지 않음
    if (cache.expiresAt > Date.now()) {
      await query(
        `INSERT INTO sign_token_cache (cache_key, token, expires_at, created_at)
         VALUES ($1, $2, $3, $4)
         ON CONFLICT (cache_key) DO UPDATE SET
           token = $2,
           expires_at = $3,
           created_at = $4`,
        [cacheKey, cache.token, cache.expiresAt, Date.now()]
      );
      cacheCount++;
    }
  }
  console.log(`  ✅ Migrated ${cacheCount} token cache entries`);

  console.log('✅ Migration completed');
}

/**
 * 마이그레이션 실행 (CLI)
 */
async function main() {
  const command = process.argv[2];

  if (command === 'init') {
    await initSchema();
  } else if (command === 'migrate') {
    // 인메모리 데이터가 있는 경우에만 실행
    console.log('⚠️  In-memory migration requires existing data');
    console.log('   This should be called from the application during startup if needed');
  } else {
    console.log('Usage:');
    console.log('  npm run migrate:init    - Initialize database schema');
    console.log('  npm run migrate:data    - Migrate in-memory data (if any)');
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}

