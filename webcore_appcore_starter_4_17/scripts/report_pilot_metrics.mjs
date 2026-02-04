#!/usr/bin/env node
/**
 * 파일럿 테넌트 지표 리포트
 * 
 * 파일럿 테넌트(default, pilot-a)의 주요 지표를 집계하여 출력합니다.
 * 
 * 사용법:
 *   node scripts/report_pilot_metrics.mjs
 *   node scripts/report_pilot_metrics.mjs --from=2025-12-01 --to=2025-12-31
 * 
 * 환경변수:
 *   DATABASE_URL - PostgreSQL 연결 문자열 (필수)
 *     예: postgres://app:app@localhost:5432/app
 * 
 * 환경변수 설정 방법:
 *   1. .env 파일 생성 (프로젝트 루트):
 *      DATABASE_URL=postgres://app:app@localhost:5432/app
 *   
 *   2. 또는 환경변수로 직접 설정:
 *      export DATABASE_URL=postgres://app:app@localhost:5432/app
 *      node scripts/report_pilot_metrics.mjs
 *   
 *   3. 또는 docker-compose 사용 시:
 *      docker-compose up -d db
 *      export DATABASE_URL=postgres://app:app@localhost:5432/app
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

const PILOT_TENANTS = ['default', 'pilot-a'];

// CLI 옵션 파싱
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { from: null, to: null };
  
  for (const arg of args) {
    if (arg.startsWith('--from=')) {
      opts.from = arg.split('=')[1];
    } else if (arg.startsWith('--to=')) {
      opts.to = arg.split('=')[1];
    }
  }
  
  // 기본값: 최근 7일
  if (!opts.from || !opts.to) {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 7);
    opts.from = opts.from || from.toISOString().split('T')[0];
    opts.to = opts.to || to.toISOString().split('T')[0];
  }
  
  return opts;
}

async function main() {
  const { from, to } = parseArgs();
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
    console.log(`\n📊 파일럿 지표 리포트 (${from} ~ ${to})\n`);
    console.log('='.repeat(60));
    
    // 1. 전체 추천 건수 (suggest 호출수)
    // 참고: suggest API는 audit 로그를 남기지 않으므로, route로 필터링
    // 실제 suggest 호출은 다른 방식으로 추적해야 할 수 있음
    const suggestResult = await pool.query(`
      SELECT COUNT(*) as count
      FROM accounting_audit_events
      WHERE tenant = ANY($1)
        AND ts >= $2::date
        AND ts < ($3::date + INTERVAL '1 day')
        AND route = '/v1/accounting/postings/suggest'
    `, [PILOT_TENANTS, from, to]);
    const suggestCount = parseInt(suggestResult.rows[0].count, 10);
    console.log(`\n1️⃣  전체 추천 건수: ${suggestCount.toLocaleString()}`);
    
    // 2. Top-1 정확도 (%)
    // 참고: 현재 payload에는 top1 정보가 없을 수 있음
    // 실제 구현 시 payload에 top1_selected 또는 selected_rank 정보를 포함해야 함
    const top1Result = await pool.query(`
      SELECT 
        COUNT(*) FILTER (WHERE payload->>'top1_selected' = 'true') as top1_count,
        COUNT(*) as total_approvals
      FROM accounting_audit_events
      WHERE tenant = ANY($1)
        AND ts >= $2::date
        AND ts < ($3::date + INTERVAL '1 day')
        AND action = 'approval_apply'
    `, [PILOT_TENANTS, from, to]);
    const top1Count = parseInt(top1Result.rows[0].top1_count || 0, 10);
    const totalApprovals = parseInt(top1Result.rows[0].total_approvals || 0, 10);
    const top1Accuracy = totalApprovals > 0 ? (top1Count / totalApprovals * 100).toFixed(2) : '0.00';
    console.log(`2️⃣  Top-1 정확도: ${top1Accuracy}% (${top1Count}/${totalApprovals})`);
    
    // 3. Top-5 정확도 (%)
    // 참고: 현재 payload에는 selected_rank 정보가 없을 수 있음
    // 실제 구현 시 payload에 selected_rank 정보를 포함해야 함
    const top5Result = await pool.query(`
      SELECT 
        COUNT(*) FILTER (WHERE (payload->>'selected_rank')::int <= 5) as top5_count,
        COUNT(*) as total_approvals
      FROM accounting_audit_events
      WHERE tenant = ANY($1)
        AND ts >= $2::date
        AND ts < ($3::date + INTERVAL '1 day')
        AND action = 'approval_apply'
    `, [PILOT_TENANTS, from, to]);
    const top5Count = parseInt(top5Result.rows[0].top5_count || 0, 10);
    const totalApprovals5 = parseInt(top5Result.rows[0].total_approvals || 0, 10);
    const top5Accuracy = totalApprovals5 > 0 ? (top5Count / totalApprovals5 * 100).toFixed(2) : '0.00';
    console.log(`3️⃣  Top-5 정확도: ${top5Accuracy}% (${top5Count}/${totalApprovals5})`);
    
    // 4. Manual Review 비율 (%)
    // 참고: suggest API는 audit 로그를 남기지 않으므로, manual_review_request만 집계
    // 분모는 전체 suggest 호출 수로 추정 (route 기반) 또는 manual_review_request + approval_apply 합계 사용
    const manualReviewResult = await pool.query(`
      SELECT 
        COUNT(*) FILTER (WHERE action = 'manual_review_request') as manual_review_count,
        COUNT(*) FILTER (WHERE route = '/v1/accounting/postings/suggest' OR action = 'manual_review_request') as total_suggestions
      FROM accounting_audit_events
      WHERE tenant = ANY($1)
        AND ts >= $2::date
        AND ts < ($3::date + INTERVAL '1 day')
    `, [PILOT_TENANTS, from, to]);
    const manualReviewCount = parseInt(manualReviewResult.rows[0].manual_review_count || 0, 10);
    const totalSuggestions = parseInt(manualReviewResult.rows[0].total_suggestions || 0, 10);
    const manualReviewRate = totalSuggestions > 0 ? (manualReviewCount / totalSuggestions * 100).toFixed(2) : '0.00';
    console.log(`4️⃣  Manual Review 비율: ${manualReviewRate}% (${manualReviewCount}/${totalSuggestions})`);
    
    // 5. Export 실패 건수
    const exportFailResult = await pool.query(`
      SELECT COUNT(*) as count
      FROM export_jobs
      WHERE tenant = ANY($1)
        AND created_at >= $2::date
        AND created_at < ($3::date + INTERVAL '1 day')
        AND status = 'failed'
    `, [PILOT_TENANTS, from, to]);
    const exportFailCount = parseInt(exportFailResult.rows[0].count, 10);
    console.log(`5️⃣  Export 실패 건수: ${exportFailCount.toLocaleString()}`);
    
    // 6. Recon 세션 중 미매칭 비율 (%)
    // matches, unmatched_bank, unmatched_ledger는 JSONB 배열
    const reconResult = await pool.query(`
      SELECT 
        COUNT(*) as total_sessions,
        SUM(
          CASE 
            WHEN jsonb_array_length(COALESCE(matches, '[]'::jsonb)) = 0 
              OR jsonb_array_length(COALESCE(unmatched_bank, '[]'::jsonb)) > 0 
              OR jsonb_array_length(COALESCE(unmatched_ledger, '[]'::jsonb)) > 0
            THEN 1 
            ELSE 0 
          END
        ) as unmatched_sessions
      FROM recon_sessions
      WHERE tenant = ANY($1)
        AND created_at >= $2::date
        AND created_at < ($3::date + INTERVAL '1 day')
    `, [PILOT_TENANTS, from, to]);
    const totalSessions = parseInt(reconResult.rows[0].total_sessions || 0, 10);
    const unmatchedSessions = parseInt(reconResult.rows[0].unmatched_sessions || 0, 10);
    const unmatchedRate = totalSessions > 0 ? (unmatchedSessions / totalSessions * 100).toFixed(2) : '0.00';
    console.log(`6️⃣  Recon 미매칭 비율: ${unmatchedRate}% (${unmatchedSessions}/${totalSessions})`);
    
    console.log('\n' + '='.repeat(60));
    console.log(`\n✅ 리포트 완료\n`);
    
  } catch (error) {
    console.error('❌ 오류 발생:', error.message);
    console.error(error);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

main();

