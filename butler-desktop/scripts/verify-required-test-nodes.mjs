import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import {
  isAbsolute,
  posix,
  relative,
  resolve,
  sep,
} from 'node:path';

import {
  parseStrictJson,
  readStrictJsonFile,
} from '../../scripts/ci/strict_json.mjs';

const REPORT_LIMIT = 32 * 1024 * 1024;
const CONTEXT_LIMIT = 64 * 1024;
const RUNNERS = new Set(['pytest', 'vitest', 'playwright', 'node']);
const PLATFORMS = new Set(['ubuntu', 'macos-15', 'windows-2025']);
const CONTEXT_KEYS = new Set([
  'schema_version',
  'repository',
  'event_name',
  'pr_number',
  'subject_head',
  'execution_commit',
  'tree',
  'object_format',
  'run_id',
  'run_attempt',
  'workflow_ref',
  'job_name',
  'runner',
  'platform',
  'command',
  'report_path',
  'report_sha256',
  'started_at',
  'finished_at',
  'tool_versions',
]);

function args(argv) {
  const result = {
    vitest: [],
    playwright: [],
    pytest: [],
    node: [],
    context: [],
  };
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    if (Object.hasOwn(result, key)) result[key].push(value);
    else result[key] = value;
  }
  return result;
}

function digest(value) {
  return createHash('sha256').update(value).digest('hex');
}

function requireRepositoryPath(value) {
  if (typeof value !== 'string' || !value || value.includes('\\')
      || isAbsolute(value) || value.split('/').some(part => (
        part === '' || part === '.' || part === '..'
      ))) {
    throw new Error('REPOSITORY_PATH_INVALID');
  }
  return value;
}

function normalizeActualFile(value, runner, repositoryRoot) {
  let normalized = String(value ?? '').replaceAll('\\', '/');
  if (isAbsolute(normalized)) {
    const rel = relative(repositoryRoot, normalized).replaceAll(sep, '/');
    if (!rel || rel === '..' || rel.startsWith('../')) {
      throw new Error('REPORT_PATH_OUTSIDE_REPOSITORY');
    }
    normalized = rel;
  }
  if (runner === 'vitest' && normalized.startsWith('src/')) {
    normalized = `butler-desktop/${normalized}`;
  }
  if (runner === 'playwright' && normalized.startsWith('e2e/')) {
    normalized = `butler-desktop/${normalized}`;
  }
  if (runner === 'playwright' && !normalized.includes('/')
      && normalized.endsWith('.spec.ts')) {
    normalized = `butler-desktop/e2e/${normalized}`;
  }
  return requireRepositoryPath(normalized);
}

function collectPytest(path, repositoryRoot) {
  const parser = resolve(repositoryRoot, 'scripts/ci/parse_junit_xml.py');
  const result = spawnSync(
    process.env.PYTHON ?? 'python',
    [parser, resolve(path)],
    {
      cwd: repositoryRoot,
      encoding: 'utf8',
      maxBuffer: REPORT_LIMIT,
    },
  );
  if (result.status !== 0) throw new Error('JUNIT_PARSE_FAILED');
  const parsed = parseStrictJson(Buffer.from(result.stdout), {
    maxBytes: REPORT_LIMIT,
    maxDepth: 16,
    maxNodes: 1_000_000,
    maxStringChars: 4_000_000,
  });
  if (!Array.isArray(parsed.nodes)) throw new Error('JUNIT_PARSE_FAILED');
  return parsed.nodes;
}

function collectVitest(report) {
  const nodes = [];
  for (const file of report.testResults ?? []) {
    for (const assertion of file.assertionResults ?? []) {
      nodes.push({
        runner: 'vitest',
        file: file.name,
        title: assertion.title,
        status: assertion.status,
      });
    }
  }
  return nodes;
}

function collectPlaywrightSuite(suite, inheritedFile, reportRoot, nodes) {
  const reportedFile = String(suite.file ?? inheritedFile).replaceAll('\\', '/');
  if (!reportedFile
      || posix.isAbsolute(reportedFile)
      || reportedFile.split('/').some(part => (
        part === '' || part === '.' || part === '..'
      ))) {
    throw new Error('PLAYWRIGHT_FILE_INVALID');
  }
  const file = reportedFile && reportRoot && !reportedFile.startsWith(`${reportRoot}/`)
    ? posix.join(reportRoot, reportedFile)
    : reportedFile;
  for (const spec of suite.specs ?? []) {
    const tests = spec.tests ?? [];
    const results = tests.flatMap(test => test.results ?? []);
    const expected = tests.every(test => (test.expectedStatus ?? 'passed') === 'passed');
    let status = 'missing';
    if (!expected) status = 'xfail';
    else if (results.some(result => [
      'failed',
      'timedOut',
      'interrupted',
    ].includes(result.status))) status = 'failed';
    else if (results.some(result => result.status === 'passed')) status = 'passed';
    else if (results.some(result => result.status === 'skipped')) status = 'skipped';
    nodes.push({ runner: 'playwright', file, title: spec.title, status });
  }
  for (const child of suite.suites ?? []) {
    collectPlaywrightSuite(child, file, reportRoot, nodes);
  }
}

function collectPlaywright(report) {
  const nodes = [];
  const configFile = String(report?.config?.configFile ?? '').replaceAll('\\', '/');
  const rootDir = String(report?.config?.rootDir ?? '').replaceAll('\\', '/');
  let reportRoot = '';
  if (configFile || rootDir) {
    if (!configFile || !rootDir || posix.basename(configFile) !== 'playwright.config.ts') {
      throw new Error('PLAYWRIGHT_CONFIG_INVALID');
    }
    const configDirectory = posix.dirname(configFile);
    const testRoot = posix.relative(configDirectory, rootDir);
    const projectDirectory = posix.basename(configDirectory);
    if (
      projectDirectory !== 'butler-desktop'
      || testRoot !== 'e2e'
      || testRoot.startsWith('../')
      || isAbsolute(testRoot)
      || posix.normalize(testRoot) !== testRoot
    ) {
      throw new Error('PLAYWRIGHT_ROOT_INVALID');
    }
    reportRoot = posix.join(projectDirectory, testRoot);
  } else if ((report.suites ?? []).length > 0) {
    throw new Error('PLAYWRIGHT_CONFIG_MISSING');
  }
  for (const suite of report.suites ?? []) {
    collectPlaywrightSuite(suite, '', reportRoot, nodes);
  }
  return nodes;
}

function collectNode(report) {
  if (report?.schema_version !== 1 || !Array.isArray(report.nodes)) {
    throw new Error('NODE_REPORT_INVALID');
  }
  return report.nodes.map(node => ({
    runner: 'node',
    file: node.file,
    title: node.title,
    status: node.status,
  }));
}

async function readReport(path, runner, repositoryRoot) {
  const metadata = await lstat(resolve(path));
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error('REPORT_FILE_TYPE_INVALID');
  }
  if (metadata.size > REPORT_LIMIT) throw new Error('REPORT_TOO_LARGE');
  const raw = await readFile(resolve(path));
  let nodes;
  if (runner === 'pytest') {
    nodes = collectPytest(path, repositoryRoot);
  } else {
    const parsed = parseStrictJson(raw, {
      maxBytes: REPORT_LIMIT,
      maxDepth: 64,
      maxNodes: 1_000_000,
      maxStringChars: 4_000_000,
    });
    if (runner === 'vitest') nodes = collectVitest(parsed);
    else if (runner === 'playwright') nodes = collectPlaywright(parsed);
    else nodes = collectNode(parsed);
  }
  return { digest: digest(raw), nodes };
}

function identityLength(algorithm) {
  if (algorithm === 'sha1') return 40;
  if (algorithm === 'sha256') return 64;
  throw new Error('OBJECT_FORMAT_INVALID');
}

function assertHex(value, length, code) {
  if (typeof value !== 'string'
      || !new RegExp(`^[0-9a-f]{${length}}$`).test(value)) {
    throw new Error(code);
  }
}

function nodeKey(node) {
  return `${node.runner}\0${node.platform}\0${node.file}\0${node.title}`;
}

function descriptionDigest(test) {
  const canonical = JSON.stringify({
    file: test.file,
    id: test.id,
    kind: test.kind,
    platform: test.platform,
    required: test.required,
    runner: test.runner,
    title: test.title,
  });
  return digest(Buffer.from(canonical));
}

function gitValue(repositoryRoot, args, code) {
  const result = spawnSync('git', args, {
    cwd: repositoryRoot,
    encoding: 'utf8',
  });
  if (result.status !== 0) throw new Error(code);
  return result.stdout.trim();
}

async function main() {
  const options = args(process.argv.slice(2));
  for (const name of [
    'manifest',
    'event',
    'head',
    'checkout-head',
    'checkout-tree',
    'object-format',
    'repository',
    'pull-request',
    'run-id',
    'run-attempt',
    'workflow-ref',
    'event-name',
  ]) {
    if (!options[name]) throw new Error('REQUIRED_INPUT_MISSING');
  }
  if (options.vitest.length !== 1 || options.playwright.length < 1
      || options.context.length < 1) {
    throw new Error('REQUIRED_REPORT_SET_MISSING');
  }
  const oidLength = identityLength(options['object-format']);
  assertHex(options.head, oidLength, 'SUBJECT_HEAD_INVALID');
  assertHex(options['checkout-head'], oidLength, 'CHECKOUT_HEAD_INVALID');
  assertHex(options['checkout-tree'], oidLength, 'CHECKOUT_TREE_INVALID');
  if (options.head !== options['checkout-head']) {
    throw new Error('CHECKOUT_HEAD_MISMATCH');
  }

  const repositoryRoot = resolve(options.root ?? process.cwd());
  const actualObjectFormat = gitValue(
    repositoryRoot,
    ['rev-parse', '--show-object-format'],
    'GIT_OBJECT_FORMAT_UNAVAILABLE',
  );
  const actualHead = gitValue(
    repositoryRoot,
    ['rev-parse', 'HEAD'],
    'GIT_HEAD_UNAVAILABLE',
  );
  const actualTree = gitValue(
    repositoryRoot,
    ['rev-parse', 'HEAD^{tree}'],
    'GIT_TREE_UNAVAILABLE',
  );
  if (actualObjectFormat !== options['object-format']
      || actualHead !== options['checkout-head']
      || actualTree !== options['checkout-tree']) {
    throw new Error('CHECKOUT_IDENTITY_MISMATCH');
  }
  const event = await readStrictJsonFile(resolve(options.event), {
    maxBytes: CONTEXT_LIMIT,
  });
  const eventHead = event?.pull_request?.head?.sha
    ?? event?.merge_group?.head_sha
    ?? event?.after
    ?? (options['event-name'] === 'workflow_dispatch' ? options.head : undefined);
  if (eventHead !== options.head) throw new Error('EVENT_HEAD_MISMATCH');
  const eventPullRequest = event?.pull_request?.number ?? 0;
  if (eventPullRequest !== Number(options['pull-request'])) {
    throw new Error('EVENT_PULL_REQUEST_MISMATCH');
  }
  if (!/^[1-9]\d*$/.test(options['run-id'])
      || !/^[1-9]\d*$/.test(options['run-attempt'])) {
    throw new Error('WORKFLOW_RUN_IDENTITY_INVALID');
  }

  const manifestRaw = await readFile(resolve(options.manifest));
  const manifest = parseStrictJson(manifestRaw, {
    maxBytes: 2 * 1024 * 1024,
    maxDepth: 32,
    maxNodes: 100_000,
  });
  if (manifest.schema_version !== 3 || typeof manifest.suite !== 'string'
      || !Number.isSafeInteger(manifest.normative_required)
      || !Number.isSafeInteger(manifest.supplemental_required)
      || !Number.isSafeInteger(manifest.required_total)
      || manifest.normative_required + manifest.supplemental_required
        !== manifest.required_total
      || !Array.isArray(manifest.retired_ids)
      || JSON.stringify(manifest.retired_ids)
        !== JSON.stringify(['FSV10-EVIDENCE-007', 'FSV10-EVIDENCE-008'])
      || !Array.isArray(manifest.tests)
      || manifest.tests.length !== manifest.required_total) {
    throw new Error('MANIFEST_INVALID');
  }
  const required = manifest.tests.filter(test => test.required === true);
  if (required.length !== manifest.tests.length || required.length === 0) {
    throw new Error('MANIFEST_REQUIRED_SET_INVALID');
  }
  const requiredIds = new Set();
  const requiredKeys = new Set();
  for (const test of required) {
    if (typeof test.id !== 'string' || !test.id
        || !RUNNERS.has(test.runner)
        || !['normative', 'supplemental_required_regression'].includes(test.kind)
        || !['ubuntu', 'windows-2025', 'macos-15'].includes(test.platform)
        || typeof test.title !== 'string' || !test.title
        || test.description_digest !== descriptionDigest(test)) {
      throw new Error('MANIFEST_NODE_INVALID');
    }
    test.file = requireRepositoryPath(test.file);
    if (requiredIds.has(test.id)) throw new Error('REQUIRED_ID_DUPLICATE');
    requiredIds.add(test.id);
    const key = nodeKey(test);
    if (requiredKeys.has(key)) throw new Error('REQUIRED_TRIPLE_DUPLICATE');
    requiredKeys.add(key);
  }

  const reportInputs = [
    ...options.vitest.map(path => ['vitest', path]),
    ...options.playwright.map(path => ['playwright', path]),
    ...options.pytest.map(path => ['pytest', path]),
    ...options.node.map(path => ['node', path]),
  ];
  const reports = [];
  const reportDigests = new Set();
  for (const [runner, path] of reportInputs) {
    const report = await readReport(path, runner, repositoryRoot);
    if (reportDigests.has(report.digest)) throw new Error('REPORT_DIGEST_DUPLICATE');
    reportDigests.add(report.digest);
    reports.push({ ...report, runner });
  }

  const contextualizedReports = new Set();
  const reportPlatforms = new Map();
  const reportByDigest = new Map(
    reports.map(report => [report.digest, report]),
  );
  for (const path of options.context) {
    const context = await readStrictJsonFile(resolve(path), {
      maxBytes: CONTEXT_LIMIT,
    });
    if (context.schema_version !== 2
        || Object.keys(context).length !== CONTEXT_KEYS.size
        || Object.keys(context).some(key => !CONTEXT_KEYS.has(key))
        || context.repository !== options.repository
        || context.event_name !== options['event-name']
        || context.pr_number !== Number(options['pull-request'])
        || context.subject_head !== options.head
        || context.execution_commit !== options['checkout-head']
        || context.tree !== options['checkout-tree']
        || context.object_format !== options['object-format']
        || context.run_id !== options['run-id']
        || !Number.isSafeInteger(context.run_attempt)
        || context.run_attempt !== Number(options['run-attempt'])
        || context.workflow_ref !== options['workflow-ref']
        || typeof context.job_name !== 'string' || !context.job_name
        || !RUNNERS.has(context.runner)
        || !PLATFORMS.has(context.platform)
        || typeof context.report_path !== 'string'
        || requireRepositoryPath(context.report_path) !== context.report_path
        || typeof context.report_sha256 !== 'string') {
      throw new Error('CONTEXT_IDENTITY_MISMATCH');
    }
    assertHex(context.report_sha256, 64, 'CONTEXT_REPORT_DIGEST_INVALID');
    if (!reportDigests.has(context.report_sha256)) {
      throw new Error('CONTEXT_REPORT_DIGEST_MISMATCH');
    }
    if (reportByDigest.get(context.report_sha256)?.runner !== context.runner) {
      throw new Error('CONTEXT_RUNNER_MISMATCH');
    }
    const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
    if (!rfc3339.test(context.started_at ?? '')
        || !rfc3339.test(context.finished_at ?? '')
        || Date.parse(context.finished_at) < Date.parse(context.started_at)) {
      throw new Error('CONTEXT_TIME_INVALID');
    }
    if (contextualizedReports.has(context.report_sha256)) {
      throw new Error('CONTEXT_REPORT_REUSED');
    }
    contextualizedReports.add(context.report_sha256);
    reportPlatforms.set(context.report_sha256, context.platform);
  }
  if (contextualizedReports.size !== reportDigests.size) {
    throw new Error('REPORT_CONTEXT_MISSING');
  }
  const actual = [];
  for (const report of reports) {
    const platform = reportPlatforms.get(report.digest);
    if (!platform) throw new Error('REPORT_CONTEXT_MISSING');
    for (const node of report.nodes) {
      actual.push({
        ...node,
        platform,
        file: normalizeActualFile(node.file, report.runner, repositoryRoot),
      });
    }
  }
  const actualKeys = new Set();
  for (const node of actual) {
    if (!RUNNERS.has(node.runner) || typeof node.title !== 'string'
        || !node.title || typeof node.status !== 'string') {
      throw new Error('ACTUAL_NODE_INVALID');
    }
    const key = nodeKey(node);
    if (actualKeys.has(key)) throw new Error('ACTUAL_NODE_DUPLICATE');
    actualKeys.add(key);
  }

  const usedActual = new Set();
  const rows = required.map(test => {
    const matches = actual
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => nodeKey(node) === nodeKey(test));
    if (matches.length !== 1) {
      return {
        id: test.id,
        executed: matches.length,
        status: matches.length === 0 ? 'missing' : 'duplicate',
      };
    }
    if (usedActual.has(matches[0].index)) {
      return { id: test.id, executed: 1, status: 'reused' };
    }
    usedActual.add(matches[0].index);
    return {
      id: test.id,
      executed: 1,
      status: matches[0].node.status,
    };
  });
  const failures = rows.filter(row => row.executed !== 1
    || row.status !== 'passed');
  const unexpected = actual.filter(node => !requiredKeys.has(nodeKey(node)));
  const exactAccounting = unexpected.length === 0
    && actual.length === required.length
    && usedActual.size === required.length;
  const summary = {
    schema_version: 3,
    suite: manifest.suite,
    subject_head: options.head,
    checkout_head: options['checkout-head'],
    checkout_tree: {
      algorithm: options['object-format'],
      hex: options['checkout-tree'],
    },
    required_total: required.length,
    actual_total: actual.length,
    matched_total: rows.filter(row => (
      row.executed === 1 && row.status === 'passed'
    )).length,
    failed_total: failures.length,
    unexpected_total: unexpected.length,
    missing: rows.filter(row => row.status === 'missing').length,
    duplicate_required_id: 0,
    duplicate_required_identity: 0,
    duplicate_actual_identity: 0,
    reused_actual: rows.filter(row => row.status === 'reused').length,
    skipped: rows.filter(row => row.status === 'skipped').length,
    deselected: rows.filter(row => row.status === 'deselected').length,
    xfail: rows.filter(row => row.status === 'xfail').length,
    failed: rows.filter(row => row.status === 'failed').length,
    errors: rows.filter(row => row.status === 'error').length,
    unexpected: unexpected.length,
    exact_accounting: exactAccounting,
    manifest_sha256: digest(manifestRaw),
    report_sha256: [...reportDigests].sort(),
    nodes: rows,
    unexpected_nodes: unexpected.map(node => ({
      runner: node.runner,
      platform: node.platform,
      file: node.file,
      title: node.title,
      status: node.status,
    })),
  };
  if (options.output) {
    await writeFile(resolve(options.output), `${JSON.stringify(summary, null, 2)}\n`);
  }
  const passed = failures.length === 0 && exactAccounting;
  console.log(`REQUIRED_TEST_NODE_AUDIT_OK=${passed ? 1 : 0}`);
  if (!passed) {
    console.log('ERROR_CODE=REQUIRED_TEST_NODE_NONPASS');
    process.exitCode = 1;
  }
}

main().catch(error => {
  console.log('REQUIRED_TEST_NODE_AUDIT_OK=0');
  console.log(`ERROR_CODE=${error.message}`);
  process.exitCode = 1;
});
