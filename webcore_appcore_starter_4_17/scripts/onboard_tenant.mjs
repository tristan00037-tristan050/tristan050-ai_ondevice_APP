#!/usr/bin/env node
/**
 * 테넌트 온보딩 스크립트
 * 
 * 사용법:
 *   node scripts/onboard_tenant.mjs --tenant=pilot-a --template=contracts/tenant_template.default.json
 * 
 * 기능:
 *   - 템플릿 기반 테넌트 설정 생성
 *   - 계정 매핑/카테고리/정책 기본값 적용
 *   - DB에 테넌트 메타데이터 저장 (향후 구현)
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = join(__dirname, '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = {};
  for (const arg of args) {
    if (arg.startsWith('--')) {
      const [key, value] = arg.slice(2).split('=');
      parsed[key] = value || true;
    }
  }
  return parsed;
}

function loadTemplate(templatePath) {
  const fullPath = join(rootDir, templatePath);
  try {
    const content = readFileSync(fullPath, 'utf-8');
    return JSON.parse(content);
  } catch (e) {
    console.error(`❌ 템플릿 로드 실패: ${templatePath}`, e.message);
    process.exit(1);
  }
}

function applyTenant(template, tenantId) {
  const config = JSON.parse(JSON.stringify(template)); // Deep copy
  config.tenant = tenantId;
  
  // 템플릿의 tenant 필드가 있으면 덮어쓰기
  if (template.tenant && template.tenant !== tenantId) {
    console.warn(`⚠️  템플릿의 tenant(${template.tenant})를 ${tenantId}로 변경합니다.`);
  }
  
  return config;
}

async function main() {
  const args = parseArgs();
  const tenant = args.tenant;
  const templatePath = args.template || 'contracts/tenant_template.default.json';

  if (!tenant) {
    console.error('❌ 오류: --tenant=<tenant-id> 필수');
    console.error('');
    console.error('사용법:');
    console.error('  node scripts/onboard_tenant.mjs --tenant=pilot-a --template=contracts/tenant_template.default.json');
    process.exit(1);
  }

  console.log(`🔄 테넌트 온보딩 시작: ${tenant}`);
  console.log(`   템플릿: ${templatePath}`);
  console.log('');

  const template = loadTemplate(templatePath);
  const config = applyTenant(template, tenant);

  console.log('✅ 생성된 테넌트 설정:');
  console.log(JSON.stringify(config, null, 2));
  console.log('');

  // TODO: DB에 저장 (tenant_metadata 테이블 등)
  // const { pool } = await import('../packages/data-pg/dist/index.js');
  // await pool.query('INSERT INTO tenant_metadata ...', [tenant, JSON.stringify(config)]);

  console.log('📋 다음 단계:');
  console.log('  1. Kubernetes Secret 생성 (어댑터 토큰 등)');
  console.log('  2. Helm values에 테넌트 추가');
  console.log('  3. OS_TENANT_ALLOWLIST_JSON에 테넌트 추가');
  console.log('  4. 네트워크 정책 적용 (egress allow-list)');
  console.log('');
  console.log(`✅ 테넌트 온보딩 완료: ${tenant}`);
}

main().catch((e) => {
  console.error('❌ 오류:', e);
  process.exit(1);
});

