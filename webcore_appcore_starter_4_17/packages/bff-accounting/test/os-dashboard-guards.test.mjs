/**
 * BFF OS Dashboard API 가드 테스트
 * R8-S1 Phase 3: OS Dashboard API 가드 검증
 * Node.js fetch 기반 테스트 (Jest 없이 실행 가능)
 */

const BASE_URL = process.env.BFF_URL || 'http://localhost:8081';
const TEST_HEADERS = {
  'X-Tenant': 'default',
  'X-User-Id': 'test-user',
  'X-User-Role': 'operator',
  'X-Api-Key': 'collector-key:operator',
};

async function test(name, fn) {
  try {
    await fn();
    console.log(`✅ ${name}`);
    return true;
  } catch (error) {
    console.error(`❌ ${name}`);
    console.error(`   ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('🧪 OS Dashboard API 가드 테스트 시작');
  console.log(`📍 BFF URL: ${BASE_URL}\n`);

  let passed = 0;
  let failed = 0;

  // 테스트 1: 기본 호출 테스트
  const test1 = await test('기본 호출 테스트 - 200 OK 및 응답 스키마 검증', async () => {
    const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    if (!body.pilot || typeof body.pilot !== 'object') {
      throw new Error('Missing or invalid pilot property');
    }
    if (!body.health || typeof body.health !== 'object') {
      throw new Error('Missing or invalid health property');
    }
    if (!body.risk || typeof body.risk !== 'object') {
      throw new Error('Missing or invalid risk property');
    }
    // manual_review는 risk 안에 manual_review_pending으로 존재
    if (typeof body.risk.manual_review_pending !== 'number') {
      throw new Error('Missing or invalid risk.manual_review_pending property');
    }
  });
  if (test1) passed++; else failed++;

  // 테스트 2: 기간 상한 테스트
  const test2 = await test('기간 상한 테스트 - 과도한 기간 요청에도 500 에러를 내지 않아야 함', async () => {
    const from = '2020-01-01';
    const to = '2030-01-01';
    const response = await fetch(
      `${BASE_URL}/v1/accounting/os/dashboard?from=${from}&to=${to}`,
      {
        method: 'GET',
        headers: TEST_HEADERS,
      }
    );

    if (response.status === 500) {
      throw new Error('Server returned 500 for large date range');
    }
    if (response.status < 200 || response.status >= 500) {
      throw new Error(`Unexpected status: ${response.status}`);
    }
  });
  if (test2) passed++; else failed++;

  // 테스트 3: 응답 스키마 회귀 테스트 (R8-S2: engine 섹션 포함)
  const test3 = await test('응답 스키마 회귀 테스트 - pilot, health, risk, engine 키 존재 확인', async () => {
    const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    const keys = Object.keys(body).sort();
    const requiredKeys = ['engine', 'health', 'pilot', 'queue', 'risk', 'window'];
    const missingKeys = requiredKeys.filter((key) => !keys.includes(key));

    if (missingKeys.length > 0) {
      throw new Error(`Missing required keys: ${missingKeys.join(', ')}`);
    }
    
    // risk 안에 manual_review_pending이 있는지 확인
    if (!body.risk || typeof body.risk.manual_review_pending !== 'number') {
      throw new Error('Missing or invalid risk.manual_review_pending property');
    }
  });
  if (test3) passed++; else failed++;

  // 테스트 3-1: engine 섹션 구조 검증 (R8-S2)
  const test3_1 = await test('engine 섹션 구조 검증 - primary_mode 및 counts 검증', async () => {
    const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    const engine = body.engine;

    if (!engine || typeof engine !== 'object') {
      throw new Error('Missing engine section');
    }

    // primary_mode는 null 또는 EngineMode 문자열이어야 함
    if (engine.primary_mode !== null && engine.primary_mode !== undefined) {
      const validModes = ['mock', 'rule', 'local-llm', 'remote'];
      if (!validModes.includes(engine.primary_mode)) {
        throw new Error(`Invalid primary_mode: ${engine.primary_mode}`);
      }
    }

    // counts 객체 검증
    if (!engine.counts || typeof engine.counts !== 'object') {
      throw new Error('Missing or invalid engine.counts');
    }

    const modes = ['mock', 'rule', 'local-llm', 'remote'];
    for (const mode of modes) {
      if (typeof engine.counts[mode] !== 'number') {
        throw new Error(`engine.counts.${mode} is not a number`);
      }
      if (engine.counts[mode] < 0) {
        throw new Error(`engine.counts.${mode} must be non-negative`);
      }
    }
  });
  if (test3_1) passed++; else failed++;

  // 테스트 4: 인증 없이 호출 시 403 Forbidden
  const test4 = await test('인증 없이 호출 시 403 Forbidden', async () => {
    const response = await fetch(`${BASE_URL}/v1/accounting/os/dashboard`, {
      method: 'GET',
    });

    if (response.status !== 403) {
      throw new Error(`Expected 403, got ${response.status}`);
    }
  });
  if (test4) passed++; else failed++;

  // 결과 출력
  console.log(`\n📊 테스트 결과: ${passed}개 통과, ${failed}개 실패`);

  if (failed > 0) {
    console.error('\n❌ 일부 테스트가 실패했습니다.');
    process.exit(1);
  } else {
    console.log('\n✅ 모든 테스트가 통과했습니다.');
    process.exit(0);
  }
}

main().catch((error) => {
  console.error('❌ 테스트 실행 중 오류:', error);
  process.exit(1);
});

