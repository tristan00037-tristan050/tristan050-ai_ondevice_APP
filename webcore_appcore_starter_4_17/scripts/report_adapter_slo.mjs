#!/usr/bin/env node
/**
 * 외부 어댑터 SLO 체크 리포트
 * 
 * 외부 어댑터의 동기화 지연 시간과 오류율을 확인합니다.
 * 
 * SLO 기준:
 * - sync 지연 ≤ 5분
 * - ExternalSyncStale 알람 유지 ≤ 10분
 * - 오류율 ≤ 5%
 * 
 * 사용법:
 *   node scripts/report_adapter_slo.mjs
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
          // 이미 환경변수가 설정되어 있지 않은 경우에만 설정
          if (!process.env[key]) {
            process.env[key] = value;
          }
        }
      }
    }
  } catch (error) {
    // .env 파일이 없어도 계속 진행 (환경변수로 직접 설정 가능)
  }
}

// 스크립트 시작 시 .env 파일 로드
loadEnvFile();

async function main() {
  const dbUrl = process.env.DATABASE_URL;
  
  if (!dbUrl) {
    console.error('❌ DATABASE_URL 환경변수가 설정되지 않았습니다.\n');
    console.error('📋 환경변수 설정 방법:\n');
    console.error('1. .env 파일 생성 (프로젝트 루트):');
    console.error('   echo "DATABASE_URL=postgres://app:app@localhost:5432/app" > .env\n');
    console.error('2. 또는 환경변수로 직접 설정:');
    console.error('   export DATABASE_URL=postgres://app:app@localhost:5432/app\n');
    console.error('3. 또는 docker-compose 사용 시:');
    console.error('   docker-compose up -d db');
    console.error('   export DATABASE_URL=postgres://app:app@localhost:5432/app\n');
    console.error('💡 예시 (docker-compose 기본값):');
    console.error('   DATABASE_URL=postgres://app:app@localhost:5432/app\n');
    process.exit(1);
  }
  
  const pool = new Pool({ connectionString: dbUrl });
  
  try {
    console.log('\n📡 외부 어댑터 SLO 체크\n');
    console.log('='.repeat(60));
    
    // 각 source별 마지막 sync 시각 및 지연 시간 조회
    // 참고: Prometheus API 연동 시 아래 쿼리 대신 PromQL 사용 가능
    // 예: external_sync_last_ts{tenant="default", source="bank-sbx"}
    //     external_sync_errors_total{tenant="default", source="bank-sbx"} / external_sync_total{tenant="default", source="bank-sbx"} * 100
    
    const sourcesResult = await pool.query(`
      SELECT DISTINCT source
      FROM external_ledger_offset
      ORDER BY source
    `);
    
    if (sourcesResult.rows.length === 0) {
      console.log('⚠️  등록된 외부 어댑터가 없습니다.\n');
      return;
    }
    
    const now = new Date();
    
    for (const row of sourcesResult.rows) {
      const source = row.source;
      
      // 마지막 sync 시각 조회 (tenant별로 최신 값)
      const offsetResult = await pool.query(`
        SELECT 
          last_ts,
          tenant,
          updated_at
        FROM external_ledger_offset
        WHERE source = $1
        ORDER BY last_ts DESC NULLS LAST, updated_at DESC NULLS LAST
        LIMIT 1
      `, [source]);
      
      let lagSeconds = null;
      let lastTs = null;
      
      if (offsetResult.rows.length > 0 && offsetResult.rows[0].last_ts) {
        lastTs = new Date(offsetResult.rows[0].last_ts);
        lagSeconds = Math.floor((now - lastTs) / 1000);
      }
      
      // 최근 1시간 동안의 동기화 실패 횟수
      // 참고: 현재 external_sync 관련 audit 이벤트는 없을 수 있음
      // 실제 구현 시 external_ledger 테이블의 데이터 업데이트 패턴이나 별도 sync 로그 테이블 사용 필요
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      
      // external_ledger의 updated_at을 기준으로 최근 동기화 활동 추정
      // 실제 오류는 별도 audit 이벤트나 sync 로그에서 추적해야 함
      const errorResult = await pool.query(`
        SELECT COUNT(*) as count
        FROM accounting_audit_events
        WHERE action = 'external_sync_error'
          AND payload->>'source' = $1
          AND ts >= $2
      `, [source, oneHourAgo]);
      
      const errorCount = parseInt(errorResult.rows[0].count, 10);
      
      // 최근 1시간 동안의 전체 동기화 시도 횟수
      // 참고: 실제 sync 이벤트가 없을 경우 external_ledger의 updated_at 기준으로 추정
      const totalResult = await pool.query(`
        SELECT COUNT(*) as count
        FROM accounting_audit_events
        WHERE action IN ('external_sync_start', 'external_sync_success', 'external_sync_error')
          AND payload->>'source' = $1
          AND ts >= $2
      `, [source, oneHourAgo]);
      
      const totalCount = parseInt(totalResult.rows[0].count, 10);
      const errorRate = totalCount > 0 ? (errorCount / totalCount * 100).toFixed(2) : '0.00';
      
      // 출력 포맷: source=bank-sbx, lag=120s, errors(last1h)=0
      const lagStr = lagSeconds !== null 
        ? `${lagSeconds}s (${Math.floor(lagSeconds / 60)}분)`
        : 'N/A (동기화 이력 없음)';
      
      const status = lagSeconds !== null && lagSeconds <= 300 ? '✅' : '⚠️';
      const errorStatus = parseFloat(errorRate) <= 5.0 ? '✅' : '⚠️';
      
      console.log(`\n${status} source=${source}`);
      if (offsetResult.rows.length > 0 && offsetResult.rows[0].tenant) {
        console.log(`   tenant=${offsetResult.rows[0].tenant}`);
      }
      console.log(`   lag=${lagStr}`);
      console.log(`   ${errorStatus} errors(last1h)=${errorCount} (${errorRate}%)`);
      
      if (lastTs) {
        console.log(`   last_sync=${lastTs.toISOString()}`);
      }
      
      // SLO 위반 경고
      if (lagSeconds !== null && lagSeconds > 300) {
        console.log(`   ⚠️  SLO 위반: sync 지연이 5분을 초과했습니다 (${Math.floor(lagSeconds / 60)}분)`);
      }
      if (totalCount > 0 && parseFloat(errorRate) > 5.0) {
        console.log(`   ⚠️  SLO 위반: 오류율이 5%를 초과했습니다 (${errorRate}%)`);
      } else if (totalCount === 0) {
        console.log(`   ℹ️  동기화 이벤트 데이터가 없습니다 (audit 이벤트 없음)`);
      }
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('\n✅ SLO 체크 완료\n');
    
    // 참고: Prometheus 연동 시 추가 메트릭
    // - external_sync_duration_seconds (히스토그램)
    // - external_sync_total (카운터)
    // - external_sync_errors_total (카운터)
    // 현재는 DB 기반으로만 체크하며, Prometheus 연동은 추후 구현 예정
    
  } catch (error) {
    console.error('❌ 오류 발생:', error.message);
    console.error(error);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

main();

