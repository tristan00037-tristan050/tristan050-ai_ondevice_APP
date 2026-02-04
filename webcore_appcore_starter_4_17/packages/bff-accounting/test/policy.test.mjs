/**
 * Policy Validator 단위 테스트 (Policy-as-Code v1)
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = join(__dirname, '../../..');

// 정책 로더 동적 import (TypeScript 컴파일 후)
async function loadValidator() {
  try {
    const validatorPath = join(ROOT, 'dist/policy/validator.js');
    return await import(validatorPath);
  } catch (e) {
    console.warn('Validator not compiled, skipping tests');
    return null;
  }
}

async function runTests() {
  const validator = await loadValidator();
  if (!validator) {
    console.log('SKIP: Validator not available');
    return;
  }

  let passed = 0;
  let failed = 0;

  // Test 1: 허용 payload PASS
  console.log('Test 1: 허용 payload');
  const test1 = validator.validateExportBody({ since: '2024-01-01', until: '2024-01-31', limitDays: 30 });
  if (test1.pass) {
    console.log('  PASS');
    passed++;
  } else {
    console.log('  FAIL:', test1);
    failed++;
  }

  // Test 2: 금지 필드 포함 시 FAIL
  console.log('Test 2: 금지 필드 포함');
  const test2 = validator.validateExportBody({ since: '2024-01-01', raw_text: 'forbidden' });
  if (!test2.pass && test2.rule_id === 'export_001') {
    console.log('  PASS: 차단됨');
    passed++;
  } else {
    console.log('  FAIL:', test2);
    failed++;
  }

  // Test 3: limitDays 초과 시 FAIL
  console.log('Test 3: limitDays 초과');
  const test3 = validator.validateExportBody({ limitDays: 100 });
  if (!test3.pass && test3.rule_id) {
    console.log('  PASS: 차단됨');
    passed++;
  } else {
    console.log('  FAIL:', test3);
    failed++;
  }

  console.log(`\n결과: ${passed} PASS, ${failed} FAIL`);
  process.exit(failed > 0 ? 1 : 0);
}

runTests().catch(e => {
  console.error('Test error:', e);
  process.exit(1);
});

