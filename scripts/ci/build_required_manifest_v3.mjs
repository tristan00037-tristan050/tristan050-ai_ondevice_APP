#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..', '..');
const source = JSON.parse(await readFile(
  resolve(root, 'butler-desktop/acceptance/required-tests.v2.json'),
  'utf8',
));

const missing = [
  ['FSV10-CANON-001', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_both_approved_inputs_exist_and_match_approved_sha256'],
  ['FSV10-CANON-002', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_archive_preflight_rejects_unsafe_entries_before_extraction'],
  ['FSV10-CANON-003', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_only_one_learning_capability_service_implementation_is_reachable'],
  ['FSV10-FILE-WIN-001', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_final_reparse_point'],
  ['FSV10-FILE-WIN-002', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_intermediate_reparse_point'],
  ['FSV10-FILE-WIN-003', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_unc_device_namespace_and_ads'],
  ['FSV10-FILE-WIN-004', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_dacl_writable_by_other_ordinary_users'],
  ['FSV10-FILE-WIN-005', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_owner_sid_mismatch'],
  ['FSV10-FILE-WIN-006', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_volume_or_file_id_change'],
  ['FSV10-E2E-002', 'playwright', 'ubuntu', 'butler-desktop/e2e/firstscreen-v5.spec.ts', '회사 배우기 실제 sidecar 시험은 route HAR service worker fetch monkey patch 프런트 응답 대체를 사용하지 않는다'],
  ['FSV10-E2E-004', 'playwright', 'ubuntu', 'butler-desktop/e2e/firstscreen-v5.spec.ts', '이전 성공 뒤 다음 조회 실패는 오래된 성공 상태를 제거하고 확인할 수 없습니다로 수렴한다'],
  ...['001', '002', '003', '004', '005', '006', '009', '010'].map(number => [
    `FSV10-EVIDENCE-${number}`,
    'node',
    'ubuntu',
    'scripts/ci/test_firstscreen_evidence_integrity.mjs',
    `FSV10-EVIDENCE-${number}`,
  ]),
  ['FSV11-EVIDENCE-011', 'node', 'ubuntu', 'scripts/ci/test_firstscreen_evidence_integrity.mjs', 'FSV11-EVIDENCE-011'],
  ['FSV11-EVIDENCE-012', 'node', 'ubuntu', 'scripts/ci/test_firstscreen_evidence_integrity.mjs', 'FSV11-EVIDENCE-012'],
];

const existing = source.tests.map(test => {
  if (test.id === 'ACC-FS90-016') {
    return { ...test, id: 'REG-FS90-016' };
  }
  if (test.id === 'ACC-FS90-017') {
    return { ...test, id: 'REG-FS90-017' };
  }
  return test;
});
const tests = [
  ...existing,
  ...missing.map(([id, runner, platform, file, title]) => ({
    id, runner, platform, file, title, required: true,
  })),
].map(test => {
  const value = {
    ...test,
    kind: test.id.startsWith('REG-')
      ? 'supplemental_required_regression'
      : 'normative',
    platform: test.platform ?? 'ubuntu',
  };
  const projection = {
    file: value.file,
    id: value.id,
    kind: value.kind,
    platform: value.platform,
    required: value.required,
    runner: value.runner,
    title: value.title,
  };
  return {
    ...value,
    description_digest: createHash('sha256')
      .update(JSON.stringify(projection))
      .digest('hex'),
  };
});

if (tests.length !== 92 || new Set(tests.map(test => test.id)).size !== 92) {
  throw new Error('REQUIRED_MANIFEST_ACCOUNTING_INVALID');
}
const document = {
  schema_version: 3,
  suite: 'firstscreen-learning-capability-v11-product-gate',
  normative_required: 90,
  supplemental_required: 2,
  required_total: 92,
  retired_ids: ['FSV10-EVIDENCE-007', 'FSV10-EVIDENCE-008'],
  tests,
};
await writeFile(
  resolve(root, 'butler-desktop/acceptance/required-tests.v3.json'),
  `${JSON.stringify(document, null, 2)}\n`,
);
console.log('REQUIRED_MANIFEST_V3_OK=1');
