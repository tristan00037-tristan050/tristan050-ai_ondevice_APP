import assert from 'node:assert/strict';
import test from 'node:test';

import {
  calculateAccounting,
  collectPytest,
  requireRepositoryPath,
  validateContext,
} from '../../butler-desktop/scripts/verify-required-test-nodes.mjs';

function node(id, title = id) {
  return {
    id,
    runner: 'node',
    platform: 'ubuntu',
    file: 'scripts/ci/test.mjs',
    title,
    status: 'passed',
  };
}

test('exact accounting rejects unexpected duplicate and nonpass nodes', () => {
  const required = [node('A'), node('B')];
  const actual = required.map(({ id: _, ...value }) => value);
  assert.equal(calculateAccounting(required, actual, 2).pass, true);
  assert.equal(
    calculateAccounting(required, [...actual, actual[0]], 2).pass,
    false,
  );
  assert.equal(
    calculateAccounting(
      required,
      [{ ...actual[0], status: 'skipped' }, actual[1]],
      2,
    ).pass,
    false,
  );
  assert.equal(
    calculateAccounting(
      required,
      [...actual, { ...actual[0], title: 'unexpected' }],
      2,
    ).pass,
    false,
  );
});

test('context contract rejects extra keys booleans and invalid order', () => {
  const expected = {
    repository: 'owner/repo',
    eventName: 'pull_request',
    pullRequest: 1,
    head: 'a'.repeat(40),
    tree: 'b'.repeat(40),
    objectFormat: 'sha1',
    runId: '2',
    runAttempt: 1,
    workflowRef: 'owner/repo/.github/workflows/x.yml@refs/pull/1/merge',
  };
  const context = {
    schema_version: 2,
    repository: expected.repository,
    event_name: expected.eventName,
    pull_request: expected.pullRequest,
    suite: 'suite',
    subject_pr_head: expected.head,
    execution_commit: expected.head,
    tree_oid: { algorithm: expected.objectFormat, hex: expected.tree },
    workflow_run_id: expected.runId,
    workflow_run_attempt: expected.runAttempt,
    workflow_ref: expected.workflowRef,
    job_name: 'job',
    runner: 'node',
    platform: 'ubuntu',
    command: 'node test',
    report_path: 'reports/node.json',
    tool_versions: { node: '24' },
    started_at: '2026-07-29T00:00:00Z',
    finished_at: '2026-07-29T00:00:01Z',
    os: 'Linux',
    arch: 'X64',
    report_sha256: 'c'.repeat(64),
  };
  assert.equal(validateContext(context, expected), 'reports/node.json');
  assert.throws(() => validateContext(
    { ...context, workflow_run_attempt: true },
    expected,
  ));
  assert.throws(() => validateContext(
    { ...context, extra: true },
    expected,
  ));
  assert.throws(() => validateContext(
    {
      ...context,
      started_at: '2026-07-29T00:00:02Z',
      finished_at: '2026-07-29T00:00:01Z',
    },
    expected,
  ));
});

test('path and JUnit parsers reject cross-platform and entity attacks', () => {
  for (const path of [
    '../result.json',
    'reports\\result.json',
    'reports/e\u0301.json',
    'reports/name:stream',
  ]) {
    assert.throws(() => requireRepositoryPath(path));
  }
  assert.throws(() => collectPytest(
    '<!DOCTYPE x [<!ENTITY y "z">]><testsuite tests="1">'
      + '<testcase classname="tests.x" name="x">&y;</testcase></testsuite>',
  ));
});
