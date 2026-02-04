#!/usr/bin/env node
/**
 * 데모용 샘플 데이터 시드 스크립트
 * 
 * accounting_audit_events, export_jobs, recon_sessions, external_ledger_offset
 * 테이블에 샘플 데이터를 삽입합니다.
 * 
 * 사용법:
 *   node scripts/seed_demo_data.mjs
 * 
 * 환경변수:
 *   DATABASE_URL - PostgreSQL 연결 문자열 (필수)
 *     예: postgres://app:app@localhost:5432/app
 */

import { Pool } from 'pg';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// .env 파일 로드 (있는 경우)
function loadEnvFile() {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  const projectRoot = join(__dirname, '..');
  const envPath = join(projectRoot, '.env');
  
  try {
    const envContent = readFileSync(envPath, 'utf8');
    const lines = envContent.split('\n');
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        const [key, ...valueParts] = trimmed.split('=');
        if (key && valueParts.length > 0) {
          const value = valueParts.join('=').trim();
          if (!process.env[key]) {
            process.env[key] = value;
          }
        }
      }
    }
  } catch (err) {
    // .env 파일이 없으면 무시
  }
}

loadEnvFile();

const DATABASE_URL = process.env.DATABASE_URL;

if (!DATABASE_URL) {
  console.error('❌ DATABASE_URL 환경변수가 설정되지 않았습니다.');
  console.error('예: export DATABASE_URL="postgres://app:app@localhost:5432/app"');
  process.exit(1);
}

const pool = new Pool({ connectionString: DATABASE_URL });

async function seedDemoData() {
  const client = await pool.connect();
  
  try {
    await client.query('BEGIN');

    console.log('📦 데모 데이터 시드 시작...\n');

    // 1. accounting_audit_events 샘플 데이터
    console.log('1) accounting_audit_events 삽입 중...');
    
    // approval_apply 3건
    await client.query(`
      INSERT INTO accounting_audit_events (tenant, action, subject_type, subject_id, actor, payload, ts)
      VALUES
        ('default', 'approval_apply', 'posting', 'p1', 'operator-1', 
         '{"top1_selected": true, "selected_rank": 1, "ai_score": 0.95}'::jsonb, NOW() - INTERVAL '1 hour'),
        ('default', 'approval_apply', 'posting', 'p2', 'operator-1',
         '{"top1_selected": false, "selected_rank": 2, "ai_score": 0.85}'::jsonb, NOW() - INTERVAL '30 minutes'),
        ('default', 'approval_apply', 'posting', 'p3', 'operator-2',
         '{"top1_selected": true, "selected_rank": 1, "ai_score": 0.92}'::jsonb, NOW() - INTERVAL '15 minutes')
      ON CONFLICT DO NOTHING;
    `);

    // manual_review_request 3건
    await client.query(`
      INSERT INTO accounting_audit_events (tenant, action, subject_type, subject_id, actor, payload, ts)
      VALUES
        ('default', 'manual_review_request', 'posting', 'p4', 'operator-1',
         '{"reason_code": "HIGH_VALUE", "amount": 50000, "currency": "KRW", "is_high_value": true}'::jsonb, NOW() - INTERVAL '2 hours'),
        ('default', 'manual_review_request', 'posting', 'p5', 'operator-1',
         '{"reason_code": "LOW_CONFIDENCE", "amount": 15000, "currency": "KRW", "is_high_value": false}'::jsonb, NOW() - INTERVAL '1 hour'),
        ('default', 'manual_review_request', 'posting', 'p6', 'operator-2',
         '{"reason_code": "HIGH_VALUE", "amount": 100000, "currency": "KRW", "is_high_value": true}'::jsonb, NOW() - INTERVAL '45 minutes')
      ON CONFLICT DO NOTHING;
    `);

    // external_sync_* 2건
    await client.query(`
      INSERT INTO accounting_audit_events (tenant, action, subject_type, subject_id, actor, payload, ts)
      VALUES
        ('default', 'external_sync_start', 'source', 'bank-sbx', 'system',
         '{"source": "bank-sbx", "tenant": "default"}'::jsonb, NOW() - INTERVAL '10 minutes'),
        ('default', 'external_sync_success', 'source', 'bank-sbx', 'system',
         '{"source": "bank-sbx", "tenant": "default", "items": 10}'::jsonb, NOW() - INTERVAL '9 minutes')
      ON CONFLICT DO NOTHING;
    `);

    // api_call (suggest route) 3건
    await client.query(`
      INSERT INTO accounting_audit_events (tenant, action, subject_type, subject_id, actor, payload, ts)
      VALUES
        ('default', 'api_call', 'route', '/v1/accounting/postings/suggest', 'operator-1',
         '{"route": "/v1/accounting/postings/suggest", "method": "POST"}'::jsonb, NOW() - INTERVAL '1 hour'),
        ('default', 'api_call', 'route', '/v1/accounting/postings/suggest', 'operator-1',
         '{"route": "/v1/accounting/postings/suggest", "method": "POST"}'::jsonb, NOW() - INTERVAL '30 minutes'),
        ('default', 'api_call', 'route', '/v1/accounting/postings/suggest', 'operator-2',
         '{"route": "/v1/accounting/postings/suggest", "method": "POST"}'::jsonb, NOW() - INTERVAL '15 minutes')
      ON CONFLICT DO NOTHING;
    `);

    console.log('   ✅ approval_apply 3건, manual_review_request 3건, external_sync_* 2건, api_call 3건 삽입 완료');

    // 2. export_jobs 샘플 데이터
    console.log('\n2) export_jobs 삽입 중...');
    
    await client.query(`
      INSERT INTO export_jobs (tenant, job_id, status, created_at, exp, sha256, manifest, filters, idem_key)
      VALUES
        ('default', 'export-demo-1', 'completed', NOW() - INTERVAL '2 hours', 
         EXTRACT(EPOCH FROM (NOW() + INTERVAL '7 days'))::bigint,
         'sha256-demo-1',
         '{"reportCount": 3, "reports": ["report-1", "report-2", "report-3"]}'::jsonb,
         '{"since": "2025-12-01T00:00:00Z", "limitDays": 7}'::jsonb,
         'idem-export-1'),
        ('default', 'export-demo-2', 'pending', NOW() - INTERVAL '30 minutes',
         EXTRACT(EPOCH FROM (NOW() + INTERVAL '7 days'))::bigint,
         'sha256-demo-2',
         '{"reportCount": 0}'::jsonb,
         '{"since": "2025-12-06T00:00:00Z", "limitDays": 1}'::jsonb,
         'idem-export-2')
      ON CONFLICT (job_id) DO NOTHING;
    `);

    console.log('   ✅ export_jobs 2건 삽입 완료');

    // 3. recon_sessions 샘플 데이터
    console.log('\n3) recon_sessions 삽입 중...');
    
    await client.query(`
      INSERT INTO recon_sessions (tenant, session_id, created_at, matches, unmatched_bank, unmatched_ledger, idem_key)
      VALUES
        ('default', 'recon-demo-1', NOW() - INTERVAL '1 hour',
         '[{"bank_id": "b1", "ledger_id": "l1", "amount": 1000}]'::jsonb,
         '[{"id": "b2", "amount": 2000, "date": "2025-12-06"}]'::jsonb,
         '[{"id": "l2", "amount": 2000, "date": "2025-12-06", "account": "8000"}, {"id": "l3", "amount": 3000, "date": "2025-12-06", "account": "8000"}]'::jsonb,
         'idem-recon-1'),
        ('default', 'recon-demo-2', NOW() - INTERVAL '3 hours',
         '[{"bank_id": "b3", "ledger_id": "l4", "amount": 5000}]'::jsonb,
         '[]'::jsonb,
         '[]'::jsonb,
         'idem-recon-2')
      ON CONFLICT (session_id) DO NOTHING;
    `);

    console.log('   ✅ recon_sessions 2건 삽입 완료');

    // 4. external_ledger_offset 샘플 데이터
    console.log('\n4) external_ledger_offset 삽입 중...');
    
    await client.query(`
      INSERT INTO external_ledger_offset (tenant, source, last_ts, updated_at)
      VALUES
        ('default', 'bank-sbx', NOW() - INTERVAL '5 minutes', NOW() - INTERVAL '5 minutes')
      ON CONFLICT (tenant, source) DO UPDATE
      SET last_ts = EXCLUDED.last_ts, updated_at = EXCLUDED.updated_at;
    `);

    console.log('   ✅ external_ledger_offset 1건 삽입 완료');

    await client.query('COMMIT');
    
    console.log('\n✅ 데모 데이터 시드 완료!');
    console.log('\n다음 명령으로 확인하세요:');
    console.log('  npm run report:pilot');
    console.log('  npm run report:adapter-slo');
    
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('❌ 시드 실패:', error.message);
    throw error;
  } finally {
    client.release();
    await pool.end();
  }
}

seedDemoData().catch((err) => {
  console.error(err);
  process.exit(1);
});

