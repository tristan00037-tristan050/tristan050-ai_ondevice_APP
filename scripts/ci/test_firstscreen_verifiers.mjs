#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import {
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  symlink,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';

import { collectPinnedActions } from './action_pins.mjs';
import { containsPrivateHomePath } from './evidence_privacy.mjs';

const root = resolve(import.meta.dirname, '..', '..');
const verifier = resolve(
  root,
  'butler-desktop/scripts/verify-required-test-nodes.mjs',
);
await mkdir(tmpdir(), { recursive: true });
const temporary = await mkdtemp(resolve(tmpdir(), 'firstscreen-verifier-'));

function git(args) {
  const result = spawnSync('git', args, { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) throw new Error('GIT_IDENTITY_UNAVAILABLE');
  return result.stdout.trim();
}

const head = git(['rev-parse', 'HEAD']);
const tree = git(['rev-parse', 'HEAD^{tree}']);
const objectFormat = git(['rev-parse', '--show-object-format']);

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function finalizeNode(node) {
  const value = {
    kind: 'normative',
    platform: 'ubuntu',
    ...node,
  };
  value.description_digest = sha256(Buffer.from(JSON.stringify({
    file: value.file,
    id: value.id,
    kind: value.kind,
    platform: value.platform,
    required: value.required,
    runner: value.runner,
    title: value.title,
  })));
  return value;
}

function finalizeManifest(manifest) {
  const tests = manifest.tests.map(finalizeNode);
  const supplemental = tests.filter(
    test => test.kind === 'supplemental_required_regression',
  ).length;
  return {
    ...manifest,
    schema_version: 3,
    normative_required: tests.length - supplemental,
    supplemental_required: supplemental,
    required_total: tests.length,
    retired_ids: ['FSV10-EVIDENCE-007', 'FSV10-EVIDENCE-008'],
    tests,
  };
}

async function json(path, value) {
  await writeFile(path, `${JSON.stringify(value)}\n`);
}

async function manifestJson(path, value) {
  const finalized = finalizeManifest(value);
  await json(path, finalized);
  return finalized;
}

async function fixture(name) {
  const dir = resolve(temporary, name);
  await mkdir(dir, { recursive: true });
  const paths = {
    dir,
    manifest: resolve(dir, 'manifest.json'),
    vitest: resolve(dir, 'vitest.json'),
    playwright: resolve(dir, 'playwright.json'),
    event: resolve(dir, 'event.json'),
    vitestContext: resolve(dir, 'vitest-context.json'),
    playwrightContext: resolve(dir, 'playwright-context.json'),
  };
  let manifest = {
    suite: 'negative-self-test',
    tests: [{
      id: 'FSV10-SELF-VALID',
      runner: 'vitest',
      file: 'butler-desktop/src/self.test.ts',
      title: 'valid node',
      required: true,
    }],
  };
  const vitest = {
    testResults: [{
      name: resolve(root, 'butler-desktop/src/self.test.ts'),
      assertionResults: [{ title: 'valid node', status: 'passed' }],
    }],
  };
  const playwright = { marker: name, suites: [] };
  manifest = await manifestJson(paths.manifest, manifest);
  await json(paths.vitest, vitest);
  await json(paths.playwright, playwright);
  await json(paths.event, {
    pull_request: { number: 886, head: { sha: head } },
  });
  const context = (reportSha, runner = 'vitest') => ({
    schema_version: 2,
    repository: 'owner/repository',
    event_name: 'pull_request',
    pr_number: 886,
    subject_head: head,
    execution_commit: head,
    tree,
    object_format: objectFormat,
    run_id: '1',
    run_attempt: 1,
    workflow_ref:
      'owner/repository/.github/workflows/firstscreen-v2-5.yml@refs/pull/886/merge',
    job_name: 'self-test',
    runner,
    platform: 'ubuntu',
    command: 'self-test',
    report_path: `reports/self-test-${runner}.json`,
    report_sha256: reportSha,
    started_at: '2026-07-29T00:00:00Z',
    finished_at: '2026-07-29T00:00:01Z',
    tool_versions: { node: process.version },
  });
  await json(
    paths.vitestContext,
    context(sha256(await readFile(paths.vitest))),
  );
  await json(
    paths.playwrightContext,
    context(sha256(await readFile(paths.playwright)), 'playwright'),
  );
  return { paths, manifest, vitest, playwright, context };
}

function invoke(paths, overrides = {}) {
  const argumentsList = [
    verifier,
    '--manifest', overrides.manifest ?? paths.manifest,
    '--vitest', overrides.vitest ?? paths.vitest,
    '--playwright', overrides.playwright ?? paths.playwright,
    '--context', overrides.vitestContext ?? paths.vitestContext,
    '--context', overrides.playwrightContext ?? paths.playwrightContext,
    '--event', overrides.event ?? paths.event,
    '--head', overrides.head ?? head,
    '--checkout-head', overrides.checkoutHead ?? head,
    '--checkout-tree', overrides.checkoutTree ?? tree,
    '--object-format', overrides.objectFormat ?? objectFormat,
    '--repository', 'owner/repository',
    '--pull-request', '886',
    '--run-id', '1',
    '--run-attempt', '1',
    '--workflow-ref',
    'owner/repository/.github/workflows/firstscreen-v2-5.yml@refs/pull/886/merge',
    '--event-name', 'pull_request',
    '--root', root,
  ];
  return spawnSync(process.execPath, argumentsList, {
    cwd: root,
    encoding: 'utf8',
  });
}

function expectFailure(result, code) {
  if (result.status === 0 || !result.stdout.includes(`ERROR_CODE=${code}`)) {
    throw new Error(`NEGATIVE_CASE_FAILED_${code}`);
  }
}

const valid = await fixture('valid');
if (invoke(valid.paths).status !== 0) throw new Error('VALID_CASE_REJECTED');

const playwrightBasename = await fixture('playwright-basename');
playwrightBasename.manifest.tests = [{
  id: 'FSV10-SELF-PLAYWRIGHT-BASENAME',
  runner: 'playwright',
  file: 'butler-desktop/e2e/self.spec.ts',
  title: 'playwright basename node',
  required: true,
}];
playwrightBasename.playwright.config = {
  configFile: '/host/checkout/butler-desktop/playwright.config.ts',
  rootDir: '/host/checkout/butler-desktop/e2e',
};
playwrightBasename.playwright.suites = [{
  file: 'self.spec.ts',
  specs: [{
    title: 'playwright basename node',
    tests: [{
      expectedStatus: 'passed',
      results: [{ status: 'passed' }],
    }],
  }],
}];
playwrightBasename.vitest.testResults[0].assertionResults = [];
playwrightBasename.manifest = await manifestJson(
  playwrightBasename.paths.manifest,
  playwrightBasename.manifest,
);
await json(playwrightBasename.paths.vitest, playwrightBasename.vitest);
await json(playwrightBasename.paths.playwright, playwrightBasename.playwright);
await json(
  playwrightBasename.paths.vitestContext,
  playwrightBasename.context(
    sha256(await readFile(playwrightBasename.paths.vitest)),
  ),
);
await json(
  playwrightBasename.paths.playwrightContext,
  playwrightBasename.context(
    sha256(await readFile(playwrightBasename.paths.playwright)),
    'playwright',
  ),
);
const playwrightBasenameResult = invoke(playwrightBasename.paths);
if (playwrightBasenameResult.status !== 0) {
  throw new Error(
    `PLAYWRIGHT_BASENAME_REJECTED:${playwrightBasenameResult.stdout}`,
  );
}

const playwrightWrongRoot = await fixture('playwright-wrong-root');
playwrightWrongRoot.playwright.config = {
  configFile: '/host/checkout/other-app/playwright.config.ts',
  rootDir: '/host/checkout/other-app/e2e',
};
playwrightWrongRoot.playwright.suites = [{
  file: 'self.spec.ts',
  specs: [],
}];
await json(playwrightWrongRoot.paths.playwright, playwrightWrongRoot.playwright);
await json(
  playwrightWrongRoot.paths.playwrightContext,
  playwrightWrongRoot.context(
    sha256(await readFile(playwrightWrongRoot.paths.playwright)),
    'playwright',
  ),
);
expectFailure(invoke(playwrightWrongRoot.paths), 'PLAYWRIGHT_ROOT_INVALID');

const playwrightAbsoluteFile = await fixture('playwright-absolute-file');
playwrightAbsoluteFile.playwright.config = {
  configFile: '/host/checkout/butler-desktop/playwright.config.ts',
  rootDir: '/host/checkout/butler-desktop/e2e',
};
playwrightAbsoluteFile.playwright.suites = [{
  file: '/host/checkout/butler-desktop/e2e/self.spec.ts',
  specs: [],
}];
await json(playwrightAbsoluteFile.paths.playwright, playwrightAbsoluteFile.playwright);
await json(
  playwrightAbsoluteFile.paths.playwrightContext,
  playwrightAbsoluteFile.context(
    sha256(await readFile(playwrightAbsoluteFile.paths.playwright)),
    'playwright',
  ),
);
expectFailure(invoke(playwrightAbsoluteFile.paths), 'PLAYWRIGHT_FILE_INVALID');

const wrongExecution = await fixture('wrong-execution');
const wrongExecutionValue = wrongExecution.context(
  sha256(await readFile(wrongExecution.paths.vitest)),
);
wrongExecutionValue.execution_commit = '0'.repeat(head.length);
await json(wrongExecution.paths.vitestContext, wrongExecutionValue);
expectFailure(invoke(wrongExecution.paths), 'CONTEXT_IDENTITY_MISMATCH');

const wrongTree = await fixture('wrong-tree');
const wrongTreeValue = wrongTree.context(
  sha256(await readFile(wrongTree.paths.vitest)),
);
wrongTreeValue.tree = '0'.repeat(tree.length);
await json(wrongTree.paths.vitestContext, wrongTreeValue);
expectFailure(invoke(wrongTree.paths), 'CONTEXT_IDENTITY_MISMATCH');

const wrongAlgorithm = await fixture('wrong-algorithm');
const wrongAlgorithmValue = wrongAlgorithm.context(
  sha256(await readFile(wrongAlgorithm.paths.vitest)),
);
wrongAlgorithmValue.object_format =
  objectFormat === 'sha1' ? 'sha256' : 'sha1';
await json(wrongAlgorithm.paths.vitestContext, wrongAlgorithmValue);
expectFailure(invoke(wrongAlgorithm.paths), 'CONTEXT_IDENTITY_MISMATCH');

const wrongRunIdentity = await fixture('wrong-run-identity');
const wrongRunIdentityValue = wrongRunIdentity.context(
  sha256(await readFile(wrongRunIdentity.paths.vitest)),
);
wrongRunIdentityValue.run_id = '2';
await json(wrongRunIdentity.paths.vitestContext, wrongRunIdentityValue);
expectFailure(invoke(wrongRunIdentity.paths), 'CONTEXT_IDENTITY_MISMATCH');

const legacyContextField = await fixture('legacy-context-field');
const legacyContextFieldValue = legacyContextField.context(
  sha256(await readFile(legacyContextField.paths.vitest)),
);
legacyContextFieldValue.suite = 'legacy-field-must-not-return';
await json(legacyContextField.paths.vitestContext, legacyContextFieldValue);
expectFailure(invoke(legacyContextField.paths), 'CONTEXT_IDENTITY_MISMATCH');

const eventMismatch = await fixture('event-mismatch');
await json(eventMismatch.paths.event, {
  pull_request: { head: { sha: '0'.repeat(head.length) } },
});
expectFailure(invoke(eventMismatch.paths), 'EVENT_HEAD_MISMATCH');

const duplicateId = await fixture('duplicate-id');
await manifestJson(duplicateId.paths.manifest, {
  ...duplicateId.manifest,
  tests: [
    duplicateId.manifest.tests[0],
    {
      ...duplicateId.manifest.tests[0],
      file: 'butler-desktop/src/other.test.ts',
    },
  ],
});
expectFailure(invoke(duplicateId.paths), 'REQUIRED_ID_DUPLICATE');

const duplicateTriple = await fixture('duplicate-triple');
await manifestJson(duplicateTriple.paths.manifest, {
  ...duplicateTriple.manifest,
  tests: [
    duplicateTriple.manifest.tests[0],
    { ...duplicateTriple.manifest.tests[0], id: 'FSV10-SELF-SECOND' },
  ],
});
expectFailure(invoke(duplicateTriple.paths), 'REQUIRED_TRIPLE_DUPLICATE');

const duplicateActual = await fixture('duplicate-actual');
duplicateActual.vitest.testResults[0].assertionResults.push({
  title: 'valid node',
  status: 'passed',
});
await json(duplicateActual.paths.vitest, duplicateActual.vitest);
await json(
  duplicateActual.paths.vitestContext,
  duplicateActual.context(sha256(await readFile(duplicateActual.paths.vitest))),
);
expectFailure(invoke(duplicateActual.paths), 'ACTUAL_NODE_DUPLICATE');

const unexpectedActual = await fixture('unexpected-actual');
unexpectedActual.vitest.testResults[0].assertionResults.push({
  title: 'unregistered node',
  status: 'passed',
});
await json(unexpectedActual.paths.vitest, unexpectedActual.vitest);
await json(
  unexpectedActual.paths.vitestContext,
  unexpectedActual.context(
    sha256(await readFile(unexpectedActual.paths.vitest)),
  ),
);
expectFailure(
  invoke(unexpectedActual.paths),
  'REQUIRED_TEST_NODE_NONPASS',
);

for (const status of ['skipped', 'failed']) {
  const nonpass = await fixture(`status-${status}`);
  nonpass.vitest.testResults[0].assertionResults[0].status = status;
  await json(nonpass.paths.vitest, nonpass.vitest);
  await json(
    nonpass.paths.vitestContext,
    nonpass.context(sha256(await readFile(nonpass.paths.vitest))),
  );
  const result = invoke(nonpass.paths);
  if (result.status === 0
      || !result.stdout.includes('REQUIRED_TEST_NODE_AUDIT_OK=0')
      || !result.stdout.includes('ERROR_CODE=REQUIRED_TEST_NODE_NONPASS')) {
    throw new Error(`NONPASS_ACCEPTED_${status}`);
  }
}

const digestMismatch = await fixture('digest-mismatch');
const badDigest = digestMismatch.context('0'.repeat(64));
await json(digestMismatch.paths.vitestContext, badDigest);
expectFailure(invoke(digestMismatch.paths), 'CONTEXT_REPORT_DIGEST_MISMATCH');

const duplicateContext = await fixture('duplicate-context');
await writeFile(
  duplicateContext.paths.vitestContext,
  `{"schema_version":1,"schema_version":1}\n`,
);
expectFailure(invoke(duplicateContext.paths), 'JSON_DUPLICATE_KEY');

const invalidPath = await fixture('invalid-path');
invalidPath.manifest.tests[0].file = '../outside.test.ts';
await manifestJson(invalidPath.paths.manifest, invalidPath.manifest);
expectFailure(invoke(invalidPath.paths), 'REPOSITORY_PATH_INVALID');

const linkedReport = await fixture('linked-report');
const realReport = resolve(linkedReport.paths.dir, 'real-vitest.json');
await writeFile(realReport, await readFile(linkedReport.paths.vitest));
await writeFile(linkedReport.paths.vitest, '{}');
await import('node:fs/promises').then(({ unlink }) => unlink(linkedReport.paths.vitest));
await symlink(realReport, linkedReport.paths.vitest);
expectFailure(invoke(linkedReport.paths), 'REPORT_FILE_TYPE_INVALID');

const macUserHome = '/' + [
  'Users', 'private-user', 'Documents', 'customer-contract.txt',
].join('/');
const linuxUserHome = '/' + [
  'home', 'private-user', 'customer-contract.txt',
].join('/');
for (const privatePath of [
  macUserHome,
  `path=${linuxUserHome}`,
  `file://${macUserHome}`,
]) {
  if (!containsPrivateHomePath(privatePath)) {
    throw new Error('PRIVATE_HOME_PATH_NOT_DETECTED');
  }
}
for (const repositoryPath of [
  'butler-desktop/src/components/home/SettingsShell.tsx',
  'diff --git a/butler_pc_core/home/store.py b/butler_pc_core/home/store.py',
  '/home/runner/work/repository/source.zip',
]) {
  if (containsPrivateHomePath(repositoryPath)) {
    throw new Error('REPOSITORY_PATH_FALSE_POSITIVE');
  }
}
const actionA = 'a'.repeat(40);
const actionB = 'b'.repeat(40);
const actionC = 'c'.repeat(40);
const pinnedActions = collectPinnedActions(`
steps:
  - uses: actions/checkout@${actionA}
  - name: Upload
    uses: actions/upload-artifact@${actionB}
`);
if (pinnedActions.get('actions/checkout') !== actionA
    || pinnedActions.get('actions/upload-artifact') !== actionB
    || pinnedActions.size !== 2) {
  throw new Error('ACTION_PIN_YAML_STYLE_NOT_DETECTED');
}
let ambiguousPinRejected = false;
try {
  collectPinnedActions(`
steps:
  - uses: actions/checkout@${actionA}
  - uses: actions/checkout@${actionC}
`);
} catch (error) {
  ambiguousPinRejected = error instanceof Error
    && error.message === 'ACTION_PIN_AMBIGUOUS';
}
if (!ambiguousPinRejected) {
  throw new Error('ACTION_PIN_AMBIGUITY_NOT_REJECTED');
}
const output = process.argv[2];
if (!output) throw new Error('OUTPUT_REQUIRED');
const gateNodes = Array.from({ length: 14 }, (_value, index) => ({
  runner: 'node',
  file: 'scripts/ci/test_firstscreen_verifiers.mjs',
  title: `FSV10-GATE-${String(index + 1).padStart(3, '0')}`,
  status: 'passed',
}));
await json(resolve(output), {
  schema_version: 1,
  nodes: gateNodes,
});
console.log('FIRSTSCREEN_VERIFIER_NEGATIVE_TESTS_OK=1');
