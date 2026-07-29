import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SOURCE = resolve(ROOT, 'butler-desktop/acceptance/required-tests.v2.json');
const TARGET = resolve(ROOT, 'butler-desktop/acceptance/required-tests.v3.json');

const additions = [
  ['FSV10-CANON-001', 'canonical-input', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_both_approved_inputs_exist_and_match_approved_sha256'],
  ['FSV10-CANON-002', 'archive-preflight', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_archive_preflight_rejects_unsafe_entries_before_extraction'],
  ['FSV10-CANON-003', 'canonical-service', 'pytest', 'ubuntu', 'tests/learning_capability/test_canonical_inputs.py', 'test_only_one_learning_capability_service_implementation_is_reachable'],
  ['FSV10-FILE-WIN-001', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_final_reparse_point'],
  ['FSV10-FILE-WIN-002', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_intermediate_reparse_point'],
  ['FSV10-FILE-WIN-003', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_unc_device_namespace_and_ads'],
  ['FSV10-FILE-WIN-004', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_dacl_writable_by_other_ordinary_users'],
  ['FSV10-FILE-WIN-005', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_owner_sid_mismatch'],
  ['FSV10-FILE-WIN-006', 'trusted-state-windows', 'pytest', 'windows-2025', 'tests/learning_capability/test_trusted_state_windows.py', 'test_windows_rejects_volume_or_file_id_change'],
  ['FSV10-E2E-002', 'product-e2e', 'playwright', 'ubuntu', 'butler-desktop/e2e/firstscreen-v5.spec.ts', '회사 배우기 실제 sidecar 시험은 route HAR service worker fetch monkey patch 프런트 응답 대체를 사용하지 않는다'],
  ['FSV10-E2E-004', 'product-e2e', 'playwright', 'ubuntu', 'butler-desktop/e2e/firstscreen-v5.spec.ts', '이전 성공 뒤 다음 조회 실패는 오래된 성공 상태를 제거하고 확인할 수 없습니다로 수렴한다'],
  ...['001', '002', '003', '004', '005', '006', '009', '010'].map(suffix => [
    `FSV10-EVIDENCE-${suffix}`,
    'evidence-contract',
    'node',
    'ubuntu',
    'scripts/ci/test_firstscreen_evidence_integrity.mjs',
    `FSV10-EVIDENCE-${suffix}`,
  ]),
  ['FSV11-EVIDENCE-011', 'evidence-contract', 'node', 'ubuntu', 'scripts/ci/test_firstscreen_evidence_integrity.mjs', 'FSV11-EVIDENCE-011'],
  ['FSV11-EVIDENCE-012', 'evidence-contract', 'node', 'ubuntu', 'scripts/ci/test_firstscreen_evidence_integrity.mjs', 'FSV11-EVIDENCE-012'],
];

function kindFor(test) {
  if (test.id.startsWith('FSV10-CANON-')) return 'canonical-service';
  if (test.id.startsWith('FSV10-SNAPSHOT-')) return 'snapshot';
  if (test.id.startsWith('FSV10-JSON-')) return 'strict-json';
  if (test.id.startsWith('FSV10-FILE-POSIX-')) return 'trusted-state-posix';
  if (test.id.startsWith('FSV10-FILE-WIN-')) return 'trusted-state-platform';
  if (test.id.startsWith('FSV10-API-')) return 'api';
  if (test.id.startsWith('FSV10-CONSUMER-')) return 'consumer-binding';
  if (test.id.startsWith('FSV10-E2E-')) return 'product-e2e';
  if (test.id.startsWith('FSV10-GATE-')) return 'verifier-gate';
  if (test.id.startsWith('REG-FS90-')) return 'supplemental-regression';
  throw new Error(`KIND_MISSING:${test.id}`);
}

function descriptionDigest(test) {
  return createHash('sha256').update([
    test.id,
    test.kind,
    test.runner,
    test.platform,
    test.file,
    test.title,
  ].join('\0')).digest('hex');
}

const source = JSON.parse(await readFile(SOURCE, 'utf8'));
const migrated = source.tests.map(raw => {
  const id = raw.id === 'ACC-FS90-016'
    ? 'REG-FS90-016'
    : raw.id === 'ACC-FS90-017'
      ? 'REG-FS90-017'
      : raw.id;
  const candidate = {
    id,
    kind: '',
    runner: raw.runner,
    platform: 'ubuntu',
    file: raw.file,
    title: raw.title,
    required: true,
    description_digest: '',
  };
  candidate.kind = kindFor(candidate);
  candidate.description_digest = descriptionDigest(candidate);
  return candidate;
});
for (const [id, kind, runner, platform, file, title] of additions) {
  const candidate = {
    id,
    kind,
    runner,
    platform,
    file,
    title,
    required: true,
    description_digest: '',
  };
  candidate.description_digest = descriptionDigest(candidate);
  migrated.push(candidate);
}
migrated.sort((left, right) => left.id.localeCompare(right.id, 'en'));
if (migrated.length !== 92 || new Set(migrated.map(test => test.id)).size !== 92) {
  throw new Error('REQUIRED_TEST_COUNT_INVALID');
}
await writeFile(TARGET, `${JSON.stringify({
  schema_version: 3,
  suite: 'firstscreen-learning-capability-v11-product-gate',
  normative_total: 90,
  supplemental_total: 2,
  tests: migrated,
}, null, 2)}\n`);
console.log('REQUIRED_TEST_V3_BUILD_OK=1');
