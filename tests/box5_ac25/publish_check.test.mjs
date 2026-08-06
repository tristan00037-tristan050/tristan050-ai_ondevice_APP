// §11 C3 — 실행 가능한 JavaScript 시험.
//
// ★정적 문자열 검색을 C3 PASS 로 세지 않는다. 이 파일이 모듈을 실제로 부른다.
// ★mock 은 production 과 ★같은 객체 모양★ 이다 — github.rest.checks.create.
//   모양이 다르면 mock 은 통과하고 실물은 안 불린다.
// 외부 npm dependency 를 추가하지 않는다(node:test 내장).

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CHECK_NAME,
  LOCKED_CANDIDATE_HEAD,
  LOCKED_INTEGRATION_BASE,
  PublicationError,
  buildSummary,
  evaluate,
  publishCheck,
} from '../../scripts/ci/ac25/publish_check.mjs';

const RECEIPT = 'a'.repeat(64);
const TREE = 'aa87b5fa82064fe651f90ab91222e8d74dcaa976';
const MERGE_COMMIT = '9ea18f7c6213b1052ce58af7d9cdce5e2e71e09d';
const MERGE_TREE = 'ae66b4274d5e644b34a1df6e09ecf6569171cdbb';

function mockGithub({ fail = false } = {}) {
  const calls = [];
  return {
    calls,
    github: {
      rest: {
        checks: {
          create: async (request) => {
            calls.push(request);
            if (fail) throw new Error('raw mock failure with /abs/path and stack');
            return { data: { id: 1 } };
          },
        },
      },
    },
  };
}

function evidence(overrides = {}) {
  return {
    AC25_TRUSTED_RESULT: 'success',
    AC25_CANDIDATE_RESULT: 'success',
    AC25_INTEGRATION_RESULT: 'success',
    AC25_TRUSTED_VERDICT: '1',
    AC25_RECEIPT_SHA256: RECEIPT,
    AC25_CANDIDATE_COMMIT: LOCKED_CANDIDATE_HEAD,
    AC25_CANDIDATE_TREE: TREE,
    AC25_MERGE_COMMIT: MERGE_COMMIT,
    AC25_MERGE_TREE: MERGE_TREE,
    AC25_PARENT_BASE: LOCKED_INTEGRATION_BASE,
    AC25_PARENT_CANDIDATE: LOCKED_CANDIDATE_HEAD,
    GITHUB_RUN_ID: '31058574141',
    ...overrides,
  };
}

const OWNER = 'tristan00037-tristan050';
const REPO = 'tristan050-ai_ondevice_APP';
const RUN_URL = `https://github.com/${OWNER}/${REPO}/actions/runs/31058574141`;

async function run(evidenceObject, options = {}) {
  const { github, calls } = mockGithub(options);
  let error = null;
  try {
    await publishCheck({ github, owner: OWNER, repo: REPO, runUrl: RUN_URL, evidence: evidenceObject });
  } catch (caught) {
    error = caught;
  }
  return { calls, error };
}

// ══ 정상 상태 — 언제나 막는 verifier 는 합격이 아니다 ═══════════════════
test('all success publishes exactly one success check', async () => {
  const { calls, error } = await run(evidence());
  assert.equal(error, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].conclusion, 'success');
  assert.equal(calls[0].name, CHECK_NAME);
  assert.equal(calls[0].head_sha, LOCKED_CANDIDATE_HEAD);
  assert.equal(calls[0].external_id, 'ac25:31058574141:final');
  assert.equal(calls[0].details_url, RUN_URL);
  assert.equal(calls[0].status, 'completed');
});

// ══ 실패 갈래마다 정확히 한 번 발행한다 ════════════════════════════════
for (const [label, override, expectedCode] of [
  ['trusted job failure', { AC25_TRUSTED_RESULT: 'failure' }, 'TRUSTED_JOB_NOT_SUCCESS'],
  ['candidate job failure', { AC25_CANDIDATE_RESULT: 'failure' }, 'CANDIDATE_JOB_NOT_SUCCESS'],
  ['integration job failure', { AC25_INTEGRATION_RESULT: 'failure' }, 'INTEGRATION_JOB_NOT_SUCCESS'],
  ['trusted job skipped', { AC25_TRUSTED_RESULT: 'skipped' }, 'TRUSTED_JOB_NOT_SUCCESS'],
  ['verdict not pass', { AC25_TRUSTED_VERDICT: '0' }, 'TRUSTED_VERDICT_NOT_PASS'],
  ['missing receipt digest', { AC25_RECEIPT_SHA256: '' }, 'PUBLISH_EVIDENCE_INCOMPLETE'],
  ['missing merge tree', { AC25_MERGE_TREE: '' }, 'PUBLISH_EVIDENCE_INCOMPLETE'],
  ['wrong parent base', { AC25_PARENT_BASE: 'b'.repeat(40) }, 'MERGE_PARENT_MISMATCH'],
  ['wrong parent candidate', { AC25_PARENT_CANDIDATE: 'c'.repeat(40) }, 'MERGE_PARENT_MISMATCH'],
  ['observed candidate mismatch', { AC25_CANDIDATE_COMMIT: 'd'.repeat(40) }, 'CANDIDATE_COORDINATE_MISMATCH'],
  ['merge equals scope end', { AC25_MERGE_COMMIT: LOCKED_CANDIDATE_HEAD }, 'MERGE_EQUALS_SCOPE_END'],
]) {
  test(`${label} still publishes one failure check`, async () => {
    const { calls, error } = await run(evidence(override));
    assert.equal(calls.length, 1, 'checks.create must be called exactly once');
    assert.equal(calls[0].conclusion, 'failure');
    assert.equal(calls[0].head_sha, LOCKED_CANDIDATE_HEAD, 'failure lands on locked head');
    assert.ok(error instanceof PublicationError);
    assert.equal(error.code, expectedCode);
  });
}

// ══ 신뢰할 수 없는 대상은 발행 자체를 하지 않는다 ══════════════════════
test('requested target mismatch never calls the API', async () => {
  const { github, calls } = mockGithub();
  await assert.rejects(
    () => publishCheck({
      github, owner: OWNER, repo: REPO, runUrl: RUN_URL,
      evidence: evidence({ AC25_REQUESTED_HEAD: 'e'.repeat(40) }),
    }),
    (error) => error.code === 'PUBLICATION_TARGET_UNTRUSTED',
  );
  assert.equal(calls.length, 0);
});

for (const [label, owner, repo] of [
  ['owner mismatch', 'attacker', REPO],
  ['repo mismatch', OWNER, 'other-repo'],
]) {
  test(`${label} never calls the API`, async () => {
    const { github, calls } = mockGithub();
    await assert.rejects(
      () => publishCheck({ github, owner, repo, runUrl: RUN_URL, evidence: evidence() }),
      (error) => error.code === 'PUBLICATION_TARGET_UNTRUSTED',
    );
    assert.equal(calls.length, 0);
  });
}

// ══ API 실패 — 짧은 코드만 남는다 ══════════════════════════════════════
test('API failure yields only a short code', async () => {
  const { calls, error } = await run(evidence(), { fail: true });
  assert.equal(calls.length, 1, 'one attempt was made');
  assert.ok(error instanceof PublicationError);
  assert.equal(error.code, 'CHECK_RUN_PUBLICATION_FAILED');
  assert.doesNotMatch(error.message, /raw mock failure/);
  assert.doesNotMatch(error.message, /\/abs\/path/);
  assert.doesNotMatch(String(error.stack || ''), /raw mock failure/);
});

// ══ summary 는 meta-only ═══════════════════════════════════════════════
test('summary carries no paths, tokens, or stacks', async () => {
  const { calls } = await run(evidence({ AC25_TRUSTED_RESULT: 'failure' }));
  const summary = calls[0].output.summary;
  // run_url 은 §9 가 요구한 details_url 이므로 slash 를 갖는다. 그 줄만 제외하고
  // ★파일 경로가 한 글자도 없어야 한다.
  const withoutRunUrl = summary
    .split('\n')
    .filter((line) => !line.startsWith('run_url='))
    .join('\n');
  assert.ok(!withoutRunUrl.includes('/'), 'no slash path outside run_url');
  assert.ok(!withoutRunUrl.includes('\\'), 'no backslash path');
  for (const forbidden of ['Traceback', 'ghp_', 'github_pat_', '.py', 'Error:', 'at Object']) {
    assert.ok(!summary.includes(forbidden), `summary must not contain ${forbidden}`);
  }
  assert.match(summary, /^verdict=0$/m);
  assert.match(summary, /^error_code=TRUSTED_JOB_NOT_SUCCESS$/m);
  assert.match(summary, /^github_merge_ref_used_for_verdict=NO$/m);
});

test('summary reports the locked coordinates only', () => {
  const verdict = evaluate(evidence());
  const summary = buildSummary(verdict, { runUrl: RUN_URL });
  assert.match(summary, new RegExp(`^candidate_commit=${LOCKED_CANDIDATE_HEAD}$`, 'm'));
  assert.match(summary, new RegExp(`^integration_base_commit=${LOCKED_INTEGRATION_BASE}$`, 'm'));
  assert.match(summary, new RegExp(`^receipt_sha256=${RECEIPT}$`, 'm'));
});

// ══ 계약 상수 ══════════════════════════════════════════════════════════
test('check name and locked target are pinned', () => {
  assert.equal(CHECK_NAME, 'box5-ac25/trusted-exact-head');
  assert.equal(LOCKED_CANDIDATE_HEAD, '61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04');
  assert.equal(LOCKED_INTEGRATION_BASE, 'afdb237e4e6e83d96a182b6c5366a2ad95949bee');
});

test('evaluate reports the first reason deterministically', () => {
  const verdict = evaluate(evidence({
    AC25_TRUSTED_RESULT: 'failure',
    AC25_CANDIDATE_RESULT: 'failure',
  }));
  assert.equal(verdict.conclusion, 'failure');
  assert.equal(verdict.errorCode, 'TRUSTED_JOB_NOT_SUCCESS');
});
