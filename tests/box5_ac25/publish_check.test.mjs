// §11 C3 · §5-3 R6-2 — 실행 가능한 JavaScript 시험.
//
// ★정적 문자열 검색을 PASS 로 세지 않는다. 이 파일이 모듈을 실제로 부른다.
// ★mock 은 production 과 ★같은 객체 모양★ 이다 — github.rest.checks.create.
// ★기대 좌표를 이 시험이 다시 적지 않는다. loader 에서 읽어 쓴다(§5-1).
//   그래야 시험과 생산이 같은 원본을 본다.
// 외부 npm dependency 를 추가하지 않는다(node:test 내장).

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CHECK_NAME,
  PublicationError,
  buildSummary,
  evaluate,
  lockedCandidateHead,
  lockedIntegrationBase,
  publishCheck,
} from '../../scripts/ci/ac25/publish_check.mjs';
import {
  CANDIDATE_COMMIT_MISMATCH,
  CANDIDATE_TREE_MISMATCH,
  CoordinateContractError,
  INTEGRATION_BASE_MISMATCH,
  MERGE_COMMIT_MISMATCH,
  MERGE_PARENT_COUNT_MISMATCH,
  MERGE_PARENT_ORDER_MISMATCH,
  MERGE_TREE_MISMATCH,
  SCHEMA_VERSION,
  STAGE_B_COORDINATE_CONTRACT_INVALID,
  canonicalBytes,
  coordinatePath,
  coordinateSourceSha256,
  evaluateObserved,
  loadCoordinates,
  loadFromBytes,
} from '../../scripts/ci/ac25/stage_b_coordinates.mjs';
import { readFileSync } from 'node:fs';

const EXPECTED = loadCoordinates();
const RECEIPT = 'a'.repeat(64);

// 감사가 직접 증거로 댄 값 — 과거 PR #904 tree. 이것으로 통과하면 안 된다.
const STALE_PR904_TREE = 'aa87b5fa82064fe651f90ab91222e8d74dcaa976';

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
    AC25_PREFLIGHT_RESULT: 'success',
    AC25_TRUSTED_RESULT: 'success',
    AC25_CANDIDATE_RESULT: 'success',
    AC25_INTEGRATION_RESULT: 'success',
    AC25_REQUIRED_JOBS_GATE: 'success',
    AC25_TRUSTED_VERDICT: '1',
    AC25_RECEIPT_SHA256: RECEIPT,
    AC25_CANDIDATE_COMMIT: EXPECTED.candidate_commit,
    AC25_CANDIDATE_TREE: EXPECTED.candidate_tree,
    AC25_MERGE_COMMIT: EXPECTED.merge_commit,
    AC25_MERGE_TREE: EXPECTED.merge_tree,
    AC25_PARENT_BASE: EXPECTED.integration_base,
    AC25_PARENT_CANDIDATE: EXPECTED.candidate_commit,
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
    await publishCheck({
      github, owner: OWNER, repo: REPO, runUrl: RUN_URL, evidence: evidenceObject,
    });
  } catch (caught) {
    error = caught;
  }
  return { calls, error };
}

// ══ §5-3 정상 상태 — 언제나 막는 verifier 는 합격이 아니다 ══════════════
test('locked five coordinates and parent order publish one success check', async () => {
  const { calls, error } = await run(evidence());
  assert.equal(error, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].conclusion, 'success');
  assert.equal(calls[0].name, CHECK_NAME);
  assert.equal(calls[0].head_sha, EXPECTED.candidate_commit);
  assert.equal(calls[0].external_id, 'ac25:31058574141:final');
  assert.equal(calls[0].details_url, RUN_URL);
  assert.equal(calls[0].status, 'completed');
});

// ══ §5-3 회귀 — 감사가 댄 과거 tree 는 반드시 FAIL ═════════════════════
test('stale PR #904 tree aa87b5fa is rejected (audit direct evidence)', async () => {
  const { calls, error } = await run(evidence({ AC25_CANDIDATE_TREE: STALE_PR904_TREE }));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].conclusion, 'failure', 'aa87b5fa 로 성공하면 C2 가 다시 열린다');
  assert.ok(error instanceof PublicationError);
  assert.equal(error.code, CANDIDATE_TREE_MISMATCH);
});

test('stale tree is not merely a format failure', () => {
  // 40자 소문자 hex 라서 형식 검사만으로는 통과한다 — 값 비교가 잡아야 한다.
  assert.match(STALE_PR904_TREE, /^[0-9a-f]{40}$/);
  assert.notEqual(STALE_PR904_TREE, EXPECTED.candidate_tree);
  const codes = evaluateObserved({
    candidateCommit: EXPECTED.candidate_commit,
    candidateTree: STALE_PR904_TREE,
    integrationBase: EXPECTED.integration_base,
    mergeCommit: EXPECTED.merge_commit,
    mergeTree: EXPECTED.merge_tree,
    mergeParents: [EXPECTED.integration_base, EXPECTED.candidate_commit],
  });
  assert.deepEqual([...codes], [CANDIDATE_TREE_MISMATCH]);
});

// ══ §5-3 다섯 좌표 각각 한 nibble 변경이 개별 FAIL ═════════════════════
function flipNibble(oid) {
  const last = oid.slice(-1);
  const replacement = last === '0' ? '1' : '0';
  return oid.slice(0, -1) + replacement;
}

for (const [label, key, code] of [
  ['candidate commit', 'candidateCommit', CANDIDATE_COMMIT_MISMATCH],
  ['candidate tree', 'candidateTree', CANDIDATE_TREE_MISMATCH],
  ['integration base', 'integrationBase', INTEGRATION_BASE_MISMATCH],
  ['merge commit', 'mergeCommit', MERGE_COMMIT_MISMATCH],
  ['merge tree', 'mergeTree', MERGE_TREE_MISMATCH],
]) {
  test(`one nibble change in ${label} fails with its own code`, () => {
    const observed = {
      candidateCommit: EXPECTED.candidate_commit,
      candidateTree: EXPECTED.candidate_tree,
      integrationBase: EXPECTED.integration_base,
      mergeCommit: EXPECTED.merge_commit,
      mergeTree: EXPECTED.merge_tree,
      mergeParents: [EXPECTED.integration_base, EXPECTED.candidate_commit],
    };
    observed[key] = flipNibble(observed[key]);
    if (key === 'integrationBase') observed.mergeParents = [observed[key], EXPECTED.candidate_commit];
    if (key === 'candidateCommit') observed.mergeParents = [EXPECTED.integration_base, observed[key]];
    const codes = [...evaluateObserved(observed)];
    assert.ok(codes.includes(code), `${label} → ${code} 가 없다: ${codes.join(',')}`);
  });
}

// ══ §5-3 형식 위반이 FAIL ══════════════════════════════════════════════
for (const [label, value] of [
  ['39 chars', EXPECTED.candidate_tree.slice(0, 39)],
  ['41 chars', `${EXPECTED.candidate_tree}0`],
  ['uppercase', EXPECTED.candidate_tree.toUpperCase()],
  ['non-hex', `z${EXPECTED.candidate_tree.slice(1)}`],
  ['all zero', '0'.repeat(40)],
  ['empty', ''],
]) {
  test(`candidate tree ${label} fails`, () => {
    const codes = [...evaluateObserved({
      candidateCommit: EXPECTED.candidate_commit,
      candidateTree: value,
      integrationBase: EXPECTED.integration_base,
      mergeCommit: EXPECTED.merge_commit,
      mergeTree: EXPECTED.merge_tree,
      mergeParents: [EXPECTED.integration_base, EXPECTED.candidate_commit],
    })];
    assert.deepEqual(codes, [CANDIDATE_TREE_MISMATCH]);
  });
}

// ══ §5-3 parent 누락·추가·역순 ═════════════════════════════════════════
for (const [label, parents, code] of [
  ['missing one parent', [EXPECTED.integration_base], MERGE_PARENT_COUNT_MISMATCH],
  ['extra parent', [EXPECTED.integration_base, EXPECTED.candidate_commit, EXPECTED.merge_commit], MERGE_PARENT_COUNT_MISMATCH],
  ['no parents', [], MERGE_PARENT_COUNT_MISMATCH],
  ['not an array', 'nope', MERGE_PARENT_COUNT_MISMATCH],
  ['reversed order', [EXPECTED.candidate_commit, EXPECTED.integration_base], MERGE_PARENT_ORDER_MISMATCH],
]) {
  test(`merge parents ${label} fails`, () => {
    const codes = [...evaluateObserved({
      candidateCommit: EXPECTED.candidate_commit,
      candidateTree: EXPECTED.candidate_tree,
      integrationBase: EXPECTED.integration_base,
      mergeCommit: EXPECTED.merge_commit,
      mergeTree: EXPECTED.merge_tree,
      mergeParents: parents,
    })];
    assert.ok(codes.includes(code), `${label} → ${codes.join(',')}`);
  });
}

test('reversed parent order also fails through publish_check', async () => {
  const { calls, error } = await run(evidence({
    AC25_PARENT_BASE: EXPECTED.candidate_commit,
    AC25_PARENT_CANDIDATE: EXPECTED.integration_base,
  }));
  assert.equal(calls[0].conclusion, 'failure');
  assert.ok(error instanceof PublicationError);
});

// ══ §5-3 job 결과 갈래마다 정확히 한 번 발행 ═══════════════════════════
for (const [label, override, expectedCode] of [
  ['preflight skipped', { AC25_PREFLIGHT_RESULT: 'skipped' }, 'PREFLIGHT_JOB_NOT_SUCCESS'],
  ['preflight failure', { AC25_PREFLIGHT_RESULT: 'failure' }, 'PREFLIGHT_JOB_NOT_SUCCESS'],
  ['preflight missing', { AC25_PREFLIGHT_RESULT: '' }, 'PREFLIGHT_JOB_NOT_SUCCESS'],
  ['required-jobs gate not success', { AC25_REQUIRED_JOBS_GATE: 'not_success' }, 'REQUIRED_JOBS_NOT_ALL_SUCCESS'],
  ['trusted job failure', { AC25_TRUSTED_RESULT: 'failure' }, 'TRUSTED_JOB_NOT_SUCCESS'],
  ['candidate job failure', { AC25_CANDIDATE_RESULT: 'failure' }, 'CANDIDATE_JOB_NOT_SUCCESS'],
  ['integration job failure', { AC25_INTEGRATION_RESULT: 'failure' }, 'INTEGRATION_JOB_NOT_SUCCESS'],
  ['trusted job skipped', { AC25_TRUSTED_RESULT: 'skipped' }, 'TRUSTED_JOB_NOT_SUCCESS'],
  ['trusted job cancelled', { AC25_TRUSTED_RESULT: 'cancelled' }, 'TRUSTED_JOB_NOT_SUCCESS'],
  ['candidate job neutral', { AC25_CANDIDATE_RESULT: 'neutral' }, 'CANDIDATE_JOB_NOT_SUCCESS'],
  ['verdict not pass', { AC25_TRUSTED_VERDICT: '0' }, 'TRUSTED_VERDICT_NOT_PASS'],
  ['missing receipt digest', { AC25_RECEIPT_SHA256: '' }, 'PUBLISH_EVIDENCE_INCOMPLETE'],
  ['missing merge tree', { AC25_MERGE_TREE: '' }, MERGE_TREE_MISMATCH],
  ['wrong parent base', { AC25_PARENT_BASE: 'b'.repeat(40) }, INTEGRATION_BASE_MISMATCH],
  ['wrong parent candidate', { AC25_PARENT_CANDIDATE: 'c'.repeat(40) }, MERGE_PARENT_ORDER_MISMATCH],
  ['observed candidate mismatch', { AC25_CANDIDATE_COMMIT: 'd'.repeat(40) }, CANDIDATE_COMMIT_MISMATCH],
  ['merge equals candidate head', { AC25_MERGE_COMMIT: EXPECTED.candidate_commit }, MERGE_COMMIT_MISMATCH],
]) {
  test(`${label} still publishes one failure check`, async () => {
    const { calls, error } = await run(evidence(override));
    assert.equal(calls.length, 1, 'checks.create must be called exactly once');
    assert.equal(calls[0].conclusion, 'failure');
    assert.equal(calls[0].head_sha, EXPECTED.candidate_commit, 'failure lands on locked head');
    assert.ok(error instanceof PublicationError);
    assert.equal(error.code, expectedCode);
  });
}

test('failure never produces a success conclusion', async () => {
  for (const override of [
    { AC25_TRUSTED_VERDICT: '0' },
    { AC25_CANDIDATE_TREE: STALE_PR904_TREE },
    { AC25_MERGE_TREE: 'f'.repeat(40) },
  ]) {
    const { calls } = await run(evidence(override));
    assert.equal(calls.length, 1);
    assert.notEqual(calls[0].conclusion, 'success');
  }
});

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

// ══ §5-3 workflow·env·CLI 가 기대값을 덮어쓰지 못한다 ══════════════════
test('evidence cannot override the expected coordinates', async () => {
  const { calls, error } = await run(evidence({
    // 공격자가 기대값처럼 보이는 키를 심어도 판정은 단일 원본만 본다
    AC25_EXPECTED_CANDIDATE_TREE: STALE_PR904_TREE,
    AC25_EXPECTED_MERGE_COMMIT: 'f'.repeat(40),
    STAGE_B_CANDIDATE_TREE: STALE_PR904_TREE,
    AC25_CANDIDATE_TREE: STALE_PR904_TREE,
  }));
  assert.equal(error.code, CANDIDATE_TREE_MISMATCH, '심은 기대값이 판정을 바꿨다');
  assert.equal(calls[0].conclusion, 'failure');
});

test('loader result is frozen so a caller cannot mutate expectations', () => {
  const coordinates = loadCoordinates();
  assert.ok(Object.isFrozen(coordinates));
  assert.throws(() => {
    'use strict';
    coordinates.candidate_tree = STALE_PR904_TREE;
  });
  assert.equal(loadCoordinates().candidate_tree, EXPECTED.candidate_tree);
});

// ══ §5-1 단일 원본 계약 ════════════════════════════════════════════════
test('the coordinate file is canonical and has exactly six keys', () => {
  const raw = readFileSync(coordinatePath());
  const parsed = JSON.parse(raw.toString('utf8'));
  assert.equal(Object.keys(parsed).length, 6);
  assert.equal(parsed.schema_version, SCHEMA_VERSION);
  assert.ok(canonicalBytes(parsed).equals(raw), 'canonical 재직렬화가 원본과 달라졌다');
  assert.ok(raw.toString('utf8').endsWith('}\n'), '끝 newline 이 없다');
});

for (const [label, text] of [
  ['duplicate key', '{\n  "schema_version": "x",\n  "schema_version": "y"\n}\n'],
  ['unknown key', JSON.stringify({ ...EXPECTED, surprise: 1 }, null, 2) + '\n'],
  ['missing key', '{\n  "schema_version": "butler.ac25.stage_b_coordinates.v1"\n}\n'],
  ['no trailing newline', JSON.stringify({
    schema_version: SCHEMA_VERSION,
    candidate_commit: EXPECTED.candidate_commit,
    candidate_tree: EXPECTED.candidate_tree,
    integration_base: EXPECTED.integration_base,
    merge_commit: EXPECTED.merge_commit,
    merge_tree: EXPECTED.merge_tree,
  }, null, 2)],
  ['compact spacing', JSON.stringify({
    schema_version: SCHEMA_VERSION,
    candidate_commit: EXPECTED.candidate_commit,
    candidate_tree: EXPECTED.candidate_tree,
    integration_base: EXPECTED.integration_base,
    merge_commit: EXPECTED.merge_commit,
    merge_tree: EXPECTED.merge_tree,
  }) + '\n'],
  ['reordered keys', JSON.stringify({
    candidate_commit: EXPECTED.candidate_commit,
    schema_version: SCHEMA_VERSION,
    candidate_tree: EXPECTED.candidate_tree,
    integration_base: EXPECTED.integration_base,
    merge_commit: EXPECTED.merge_commit,
    merge_tree: EXPECTED.merge_tree,
  }, null, 2) + '\n'],
  ['all zero oid', JSON.stringify({
    schema_version: SCHEMA_VERSION,
    candidate_commit: '0'.repeat(40),
    candidate_tree: EXPECTED.candidate_tree,
    integration_base: EXPECTED.integration_base,
    merge_commit: EXPECTED.merge_commit,
    merge_tree: EXPECTED.merge_tree,
  }, null, 2) + '\n'],
  ['not json', 'nope'],
  ['array root', '[]'],
]) {
  test(`coordinate contract rejects ${label}`, () => {
    assert.throws(
      () => loadFromBytes(Buffer.from(text, 'utf8')),
      (error) => error instanceof CoordinateContractError
        && error.code === STAGE_B_COORDINATE_CONTRACT_INVALID,
    );
  });
}

test('coordinate source digest is reported for the receipt', () => {
  const digest = coordinateSourceSha256();
  assert.match(digest, /^[0-9a-f]{64}$/);
});

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

// ══ summary 는 meta-only 이고 전체 OID 를 반복하지 않는다(§5-2) ═════════
test('summary carries no paths, tokens, stacks, or full OIDs', async () => {
  const { calls } = await run(evidence({ AC25_TRUSTED_RESULT: 'failure' }));
  const summary = calls[0].output.summary;
  const withoutRunUrl = summary
    .split('\n')
    .filter((line) => !line.startsWith('run_url='))
    .join('\n');
  assert.ok(!withoutRunUrl.includes('/'), 'no slash path outside run_url');
  assert.ok(!withoutRunUrl.includes('\\'), 'no backslash path');
  for (const forbidden of ['Traceback', 'ghp_', 'github_pat_', '.py', 'Error:', 'at Object']) {
    assert.ok(!summary.includes(forbidden), `summary must not contain ${forbidden}`);
  }
  // ★전체 40자 OID 를 로그에 반복하지 않는다
  for (const oid of [
    EXPECTED.candidate_commit, EXPECTED.candidate_tree, EXPECTED.integration_base,
    EXPECTED.merge_commit, EXPECTED.merge_tree,
  ]) {
    assert.ok(!summary.includes(oid), `summary must not repeat full OID ${oid.slice(0, 8)}…`);
  }
  assert.match(summary, /^verdict=0$/m);
  assert.match(summary, /^error_code=TRUSTED_JOB_NOT_SUCCESS$/m);
  assert.match(summary, /^github_merge_ref_used_for_verdict=NO$/m);
  assert.match(summary, /^coordinate_ssot_sha256=[0-9a-f]{64}$/m);
});

test('summary reports short coordinates and the receipt digest', () => {
  const verdict = evaluate(evidence());
  const summary = buildSummary(verdict, { runUrl: RUN_URL });
  assert.match(summary, new RegExp(`^candidate_commit_short=${EXPECTED.candidate_commit.slice(0, 8)}$`, 'm'));
  assert.match(summary, new RegExp(`^integration_base_short=${EXPECTED.integration_base.slice(0, 8)}$`, 'm'));
  assert.match(summary, new RegExp(`^receipt_sha256=${RECEIPT}$`, 'm'));
});

// ══ 계약 상수는 단일 원본에서만 온다 ═══════════════════════════════════
test('check name is pinned and locked target comes from the single source', () => {
  assert.equal(CHECK_NAME, 'box5-ac25/trusted-exact-head');
  assert.equal(lockedCandidateHead(), EXPECTED.candidate_commit);
  assert.equal(lockedIntegrationBase(), EXPECTED.integration_base);
});

test('publish_check does not hard-code any 40-hex coordinate', () => {
  const source = readFileSync(
    new URL('../../scripts/ci/ac25/publish_check.mjs', import.meta.url), 'utf8',
  );
  const literals = source.match(/[0-9a-f]{40}/g) || [];
  assert.deepEqual(literals, [], `기대 좌표가 복제되었다: ${literals.join(',')}`);
});

test('evaluate reports the first reason deterministically', () => {
  const verdict = evaluate(evidence({
    AC25_TRUSTED_RESULT: 'failure',
    AC25_CANDIDATE_RESULT: 'failure',
  }));
  assert.equal(verdict.conclusion, 'failure');
  assert.equal(verdict.errorCode, 'TRUSTED_JOB_NOT_SUCCESS');
});
