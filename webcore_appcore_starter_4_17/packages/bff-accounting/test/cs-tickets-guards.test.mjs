/**
 * BFF CS Tickets API 가드 테스트
 * R9-S1: CS Tickets API 가드 검증
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
  console.log('🧪 CS Tickets API 가드 테스트 시작');
  console.log(`📍 BFF URL: ${BASE_URL}\n`);

  let passed = 0;
  let failed = 0;

  // 테스트 1: 인증 없이 호출 시 403 또는 401
  const test1 = await test('인증 없이 호출 시 403 또는 401', async () => {
    const response = await fetch(`${BASE_URL}/v1/cs/tickets`, {
      method: 'GET',
    });

    if (response.status !== 403 && response.status !== 401) {
      throw new Error(`Expected 403 or 401, got ${response.status}`);
    }
  });
  if (test1) passed++; else failed++;

  // 테스트 2: 올바른 헤더로 호출 시 200, items 배열이 존재하고 각 항목에 id/subject/status가 있다
  const test2 = await test('올바른 헤더로 호출 시 200, items 배열 및 필수 필드 검증', async () => {
    const response = await fetch(`${BASE_URL}/v1/cs/tickets`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    if (!body.items || !Array.isArray(body.items)) {
      throw new Error('Missing or invalid items property');
    }

    // 각 항목에 필수 필드가 있는지 확인
    for (const item of body.items) {
      if (typeof item.id !== 'number') {
        throw new Error('Missing or invalid id property');
      }
      if (typeof item.subject !== 'string') {
        throw new Error('Missing or invalid subject property');
      }
      if (!['open', 'pending', 'closed'].includes(item.status)) {
        throw new Error(`Invalid status: ${item.status}`);
      }
      if (typeof item.createdAt !== 'string') {
        throw new Error('Missing or invalid createdAt property');
      }
    }
  });
  if (test2) passed++; else failed++;

  // 테스트 3: status 필터가 적용되면 해당 status 이외의 티켓은 나오지 않는다
  const test3 = await test('status 필터 검증 - open 필터 시 open 티켓만 반환', async () => {
    const response = await fetch(`${BASE_URL}/v1/cs/tickets?status=open`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    if (!body.items || !Array.isArray(body.items)) {
      throw new Error('Missing or invalid items property');
    }

    // 모든 항목이 open 상태인지 확인
    for (const item of body.items) {
      if (item.status !== 'open') {
        throw new Error(`Expected all items to have status 'open', but found '${item.status}'`);
      }
    }
  });
  if (test3) passed++; else failed++;

  // 테스트 4: 잘못된 status 파라미터 시 400
  const test4 = await test('잘못된 status 파라미터 시 400', async () => {
    const response = await fetch(`${BASE_URL}/v1/cs/tickets?status=invalid`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 400) {
      throw new Error(`Expected 400, got ${response.status}`);
    }

    const body = await response.json();
    if (!body.error_code || body.error_code !== 'INVALID_STATUS') {
      throw new Error('Expected error_code INVALID_STATUS');
    }
  });
  if (test4) passed++; else failed++;

  // 테스트 5: limit/offset 파라미터 검증
  const test5 = await test('limit/offset 파라미터 검증', async () => {
    const response = await fetch(`${BASE_URL}/v1/cs/tickets?limit=5&offset=0`, {
      method: 'GET',
      headers: TEST_HEADERS,
    });

    if (response.status !== 200) {
      throw new Error(`Expected 200, got ${response.status}`);
    }

    const body = await response.json();
    if (!body.items || !Array.isArray(body.items)) {
      throw new Error('Missing or invalid items property');
    }

    // limit이 적용되었는지 확인 (최대 5개)
    if (body.items.length > 5) {
      throw new Error(`Expected at most 5 items, got ${body.items.length}`);
    }
  });
  if (test5) passed++; else failed++;

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

