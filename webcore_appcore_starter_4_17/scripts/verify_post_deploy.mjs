#!/usr/bin/env node

/**
 * 포스트 배포 검증 스크립트
 * 헬스, 레디, 메트릭 엔드포인트 검증
 */

import assert from 'node:assert/strict';

const base = process.env.BFF_URL ?? 'http://localhost:8081';
const tenant = process.env.TENANT_ID ?? 'default';

const must200 = async (path) => {
  try {
    const r = await globalThis.fetch(`${base}${path}`, {
      headers: { 'X-Tenant': tenant },
      signal: AbortSignal.timeout(5000), // 5초 타임아웃
    });
    assert.equal(r.status, 200, `${path} -> ${r.status}`);
    return r.text();
  } catch (err) {
    if (err.cause?.code === 'ECONNREFUSED') {
      console.error(`❌ 연결 실패: ${base}${path}`);
      console.error(`   BFF 서버가 실행 중인지 확인하세요.`);
      console.error(`   예: docker run -d --name bff -p 8081:8081 ...`);
      process.exit(1);
    }
    throw err;
  }
};

console.log(`🔍 BFF 검증 시작: ${base}`);
await must200('/health');
console.log('✅ /health OK');
await must200('/ready');
console.log('✅ /ready OK');
const m = await must200('/metrics');
assert.match(m, /http_request_duration_seconds/, 'metrics missing');
console.log('✅ /metrics OK (http_request_duration_seconds 포함)');

console.log('\n✅ post-deploy verification passed');

