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
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  parseStrictJson,
  readStrictJsonFile,
} from '../../scripts/ci/strict_json.mjs';

const REPORT_LIMIT = 32 * 1024 * 1024;
const CONTEXT_LIMIT = 64 * 1024;
const RUNNERS = new Set(['pytest', 'vitest', 'playwright', 'node']);
const PLATFORMS = new Set(['ubuntu', 'macos-15', 'windows-2025']);
// 경로 격리(개발지시서 v13.1 §9, 총괄기획팀 2026-07-30 지시): 보호 검증기 사슬이
// 검사받는 제품 PR 이 편집하는 도구를 신뢰 경계 안으로 들이지 않도록, JUnit 파서를
// 독립 보호판(trusted_parse_junit_xml.py, main 강화판·stdin 지원)으로 고정한다.
// 제품판 scripts/ci/parse_junit_xml.py 를 느슨하게 바꿔도 이 사슬은 영향받지 않는다.
const JUNIT_PARSER = fileURLToPath(new URL(
  '../../scripts/ci/trusted_parse_junit_xml.py',
  import.meta.url,
));
const WINDOWS_RESERVED = new Set([
  'CON',
  'PRN',
  'AUX',
  'NUL',
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
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

export function requireRepositoryPath(value) {
  const parts = typeof value === 'string' ? value.split('/') : [];
  if (typeof value !== 'string' || !value || value.includes('\\')
      || value.normalize('NFC') !== value
      || isAbsolute(value) || parts.some(part => (
        part === ''
        || part === '.'
        || part === '..'
        || part.endsWith(' ')
        || part.endsWith('.')
        || part.includes(':')
        || WINDOWS_RESERVED.has(part.split('.', 1)[0].toUpperCase())
      ))) {
    throw new Error('REPOSITORY_PATH_INVALID');
  }
  return value;
}

export function normalizeActualFile(
  value,
  runner,
  repositoryRoot,
  trustedMode = false,
) {
  let normalized = String(value ?? '').replaceAll('\\', '/');
  if (isAbsolute(normalized) || /^[A-Za-z]:\//.test(normalized)) {
    const rel = relative(repositoryRoot, normalized).replaceAll(sep, '/');
    if (!rel || rel === '..' || rel.startsWith('../')) {
      if (!trustedMode) throw new Error('REPORT_PATH_OUTSIDE_REPOSITORY');
      const candidates = [
        '/butler-desktop/',
        '/tests/',
        '/scripts/',
      ].flatMap(marker => {
        const index = normalized.lastIndexOf(marker);
        return index < 0 ? [] : [normalized.slice(index + 1)];
      });
      if (candidates.length !== 1) {
        throw new Error('REPORT_PATH_OUTSIDE_REPOSITORY');
      }
      [normalized] = candidates;
    } else {
      normalized = rel;
    }
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

export function collectPytest(xml) {
  const result = spawnSync(
    process.env.PYTHON ?? 'python3',
    [JUNIT_PARSER, '-'],
    {
      encoding: 'utf8',
      input: xml,
      maxBuffer: REPORT_LIMIT,
    },
  );
  if (result.status !== 0) throw new Error('XML_PARSE_INVALID');
  const parsed = parseStrictJson(Buffer.from(result.stdout), {
    maxBytes: REPORT_LIMIT,
    maxDepth: 16,
    maxNodes: 1_000_000,
    maxStringChars: 4_000_000,
  });
  if (!Array.isArray(parsed.nodes)) throw new Error('XML_PARSE_INVALID');
  return parsed.nodes;
}

export function collectVitest(report) {
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

export function collectPlaywright(report) {
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

export function collectNode(report) {
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

async function readReport(path, runner) {
  const metadata = await lstat(resolve(path));
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error('REPORT_FILE_TYPE_INVALID');
  }
  if (metadata.size > REPORT_LIMIT) throw new Error('REPORT_TOO_LARGE');
  const raw = await readFile(resolve(path));
  if (raw.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))) {
    throw new Error('REPORT_BOM_FORBIDDEN');
  }
  let nodes;
  if (runner === 'pytest') {
    nodes = collectPytest(new TextDecoder('utf-8', { fatal: true }).decode(raw));
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
  return { digest: digest(raw), nodes, path: resolve(path) };
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
  'tool_versions',
  'started_at',
  'finished_at',
  'report_sha256',
]);

export function validateContext(context, expected) {
  if (typeof context !== 'object' || context === null || Array.isArray(context)
      || Object.keys(context).length !== CONTEXT_KEYS.size
      || Object.keys(context).some(key => !CONTEXT_KEYS.has(key))
      || context.schema_version !== 2
      || context.repository !== expected.repository
      || context.event_name !== expected.eventName
      || context.pr_number !== expected.pullRequest
      || context.subject_head !== expected.head
      || context.execution_commit !== expected.head
      || context.tree !== expected.tree
      || context.object_format !== expected.objectFormat
      || context.run_id !== expected.runId
      || !Number.isSafeInteger(context.run_attempt)
      || context.run_attempt !== expected.runAttempt
      || context.workflow_ref !== expected.workflowRef
      || typeof context.job_name !== 'string' || !context.job_name
      || !RUNNERS.has(context.runner)
      || !PLATFORMS.has(context.platform)
      || typeof context.command !== 'string' || !context.command
      || typeof context.report_path !== 'string'
      || typeof context.report_sha256 !== 'string'
      || typeof context.started_at !== 'string'
      || typeof context.finished_at !== 'string'
      || typeof context.tool_versions !== 'object'
      || context.tool_versions === null
      || Array.isArray(context.tool_versions)
      || Object.keys(context.tool_versions).length === 0
      || Object.values(context.tool_versions).some(value => (
        typeof value !== 'string' || !value || value.length > 256
      ))) {
    throw new Error('CONTEXT_IDENTITY_MISMATCH');
  }
  const startedAt = Date.parse(context.started_at);
  const finishedAt = Date.parse(context.finished_at);
  if (!Number.isFinite(startedAt)
      || !Number.isFinite(finishedAt)
      || finishedAt < startedAt) {
    throw new Error('CONTEXT_TIME_INVALID');
  }
  assertHex(context.report_sha256, 64, 'CONTEXT_REPORT_DIGEST_INVALID');
  return requireRepositoryPath(context.report_path);
}

export function validateReportBinding(context, reportDigests, reportRunners) {
  if (!reportDigests.has(context.report_sha256)) {
    throw new Error('CONTEXT_REPORT_DIGEST_MISMATCH');
  }
  if (reportRunners.get(context.report_sha256) !== context.runner) {
    throw new Error('CONTEXT_RUNNER_MISMATCH');
  }
}

export function nodeKey(node) {
  return `${node.runner}\0${node.platform}\0${node.file}\0${node.title}`;
}

function descriptionDigest(node) {
  return digest(JSON.stringify({
    file: node.file,
    id: node.id,
    kind: node.kind,
    platform: node.platform,
    required: node.required,
    runner: node.runner,
    title: node.title,
  }));
}

export function calculateAccounting(required, actual, expectedTotal) {
  const requiredIds = new Set();
  const requiredKeys = new Set();
  let duplicateRequiredId = 0;
  let duplicateRequiredIdentity = 0;
  for (const node of required) {
    if (requiredIds.has(node.id)) duplicateRequiredId += 1;
    requiredIds.add(node.id);
    const key = nodeKey(node);
    if (requiredKeys.has(key)) duplicateRequiredIdentity += 1;
    requiredKeys.add(key);
  }
  const actualKeys = new Set();
  let duplicateActualIdentity = 0;
  for (const node of actual) {
    const key = nodeKey(node);
    if (actualKeys.has(key)) duplicateActualIdentity += 1;
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
  const countStatus = status => actual.filter(node => node.status === status).length;
  const counters = {
    required_total: required.length,
    actual_total: actual.length,
    missing: rows.filter(row => row.status === 'missing').length,
    duplicate_required_id: duplicateRequiredId,
    duplicate_required_identity: duplicateRequiredIdentity,
    duplicate_actual_identity: duplicateActualIdentity,
    reused_actual: rows.filter(row => row.status === 'reused').length,
    skipped: countStatus('skipped'),
    deselected: countStatus('deselected'),
    xfail: countStatus('xfail'),
    failed: countStatus('failed'),
    errors: countStatus('error'),
    unexpected: actual.filter(node => !requiredKeys.has(nodeKey(node))).length,
  };
  const pass = failures.length === 0
    && Object.entries(counters).every(([name, value]) => (
      name === 'required_total' || name === 'actual_total'
        ? value === expectedTotal
        : value === 0
    ));
  return { counters, failures, pass, rows };
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
    'event-name',
    'pull-request',
    'run-id',
    'run-attempt',
    'workflow-ref',
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
  const trustedMode = options['trusted-mode'] === '1';
  if (trustedMode) {
    if (!options['trusted-verifier-head']
        || !options['trusted-verifier-tree']
        || !options['evidence-root']) {
      throw new Error('TRUSTED_INPUT_MISSING');
    }
    assertHex(
      options['trusted-verifier-head'],
      oidLength,
      'TRUSTED_VERIFIER_HEAD_INVALID',
    );
    assertHex(
      options['trusted-verifier-tree'],
      oidLength,
      'TRUSTED_VERIFIER_TREE_INVALID',
    );
  }
  if (actualObjectFormat !== options['object-format']
      || actualHead !== (
        trustedMode
          ? options['trusted-verifier-head']
          : options['checkout-head']
      )
      || actualTree !== (
        trustedMode
          ? options['trusted-verifier-tree']
          : options['checkout-tree']
      )) {
    throw new Error('CHECKOUT_IDENTITY_MISMATCH');
  }
  const event = await readStrictJsonFile(resolve(options.event), {
    maxBytes: CONTEXT_LIMIT,
  });
  const eventHead = event?.pull_request?.head?.sha
    ?? event?.merge_group?.head_sha
    ?? event?.after;
  if (eventHead !== options.head) throw new Error('EVENT_HEAD_MISMATCH');

  const manifestRaw = await readFile(resolve(options.manifest));
  const manifest = parseStrictJson(manifestRaw, {
    maxBytes: 2 * 1024 * 1024,
    maxDepth: 32,
    maxNodes: 100_000,
  });
  const selfTest = options['self-test'] === '1';
  if (manifest.schema_version !== 3
      || typeof manifest.normative_required !== 'number'
      || typeof manifest.supplemental_required !== 'number'
      || manifest.normative_required + manifest.supplemental_required
      !== manifest.tests?.length
      || manifest.required_total !== manifest.tests?.length
      || (!selfTest && (
        manifest.normative_required !== 90
        || manifest.supplemental_required !== 2
        || manifest.required_total !== 92
        || manifest.tests?.length !== 92
        || manifest.suite
        !== 'firstscreen-learning-capability-v11-product-gate'
      ))
      || typeof manifest.suite !== 'string'
      || !Array.isArray(manifest.tests)) {
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
        || typeof test.kind !== 'string' || !test.kind
        || !RUNNERS.has(test.runner)
        || !PLATFORMS.has(test.platform)
        || typeof test.title !== 'string' || !test.title) {
      throw new Error('MANIFEST_NODE_INVALID');
    }
    test.file = requireRepositoryPath(test.file);
    if (test.description_digest !== descriptionDigest(test)) {
      throw new Error('MANIFEST_DESCRIPTION_DIGEST_INVALID');
    }
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
    const report = await readReport(path, runner);
    if (reportDigests.has(report.digest)) throw new Error('REPORT_DIGEST_DUPLICATE');
    reportDigests.add(report.digest);
    reports.push({
      runner,
      digest: report.digest,
      nodes: report.nodes,
      path: report.path,
    });
  }

  const contextualizedReports = new Set();
  const reportPlatforms = new Map();
  const reportPaths = new Map();
  const reportRunners = new Map(
    reports.map(report => [report.digest, report.runner]),
  );
  const expectedContext = {
    repository: event.repository?.full_name,
    eventName: options['event-name'],
    pullRequest: Number(options['pull-request']),
    head: options.head,
    tree: options['checkout-tree'],
    objectFormat: options['object-format'],
    runId: options['run-id'],
    runAttempt: Number(options['run-attempt']),
    workflowRef: options['workflow-ref'],
  };
  for (const path of options.context) {
    const context = await readStrictJsonFile(resolve(path), {
      maxBytes: CONTEXT_LIMIT,
    });
    const reportPath = validateContext(context, expectedContext);
    validateReportBinding(context, reportDigests, reportRunners);
    if (contextualizedReports.has(context.report_sha256)) {
      throw new Error('CONTEXT_REPORT_REUSED');
    }
    contextualizedReports.add(context.report_sha256);
    reportPlatforms.set(context.report_sha256, context.platform);
    reportPaths.set(context.report_sha256, reportPath);
  }
  if (contextualizedReports.size !== reportDigests.size) {
    throw new Error('REPORT_CONTEXT_MISSING');
  }
  const actual = [];
  const reportRoot = trustedMode
    ? resolve(options['evidence-root'])
    : repositoryRoot;
  for (const report of reports) {
    const platform = reportPlatforms.get(report.digest);
    if (!platform) throw new Error('REPORT_PLATFORM_MISSING');
    const suppliedPath = relative(reportRoot, report.path).replaceAll(sep, '/');
    if (requireRepositoryPath(suppliedPath) !== reportPaths.get(report.digest)) {
      throw new Error('CONTEXT_REPORT_PATH_MISMATCH');
    }
    for (const node of report.nodes) {
      actual.push({
        ...node,
        platform,
        file: normalizeActualFile(
          node.file,
          report.runner,
          repositoryRoot,
          trustedMode,
        ),
      });
    }
  }
  const actualKeys = new Set();
  for (const node of actual) {
    if (!RUNNERS.has(node.runner)
        || !PLATFORMS.has(node.platform)
        || typeof node.title !== 'string'
        || !node.title
        || typeof node.status !== 'string') {
      throw new Error('ACTUAL_NODE_INVALID');
    }
    const key = nodeKey(node);
    if (actualKeys.has(key)) throw new Error('ACTUAL_NODE_DUPLICATE');
    actualKeys.add(key);
  }

  const expectedTotal = selfTest ? required.length : 92;
  const accounting = calculateAccounting(required, actual, expectedTotal);
  const {
    counters,
    failures,
    pass: accountingPass,
    rows,
  } = accounting;
  const summary = {
    schema_version: 3,
    suite: manifest.suite,
    subject_head: options.head,
    checkout_head: options['checkout-head'],
    checkout_tree: {
      algorithm: options['object-format'],
      hex: options['checkout-tree'],
    },
    ...counters,
    matched_total: rows.filter(row => (
      row.executed === 1 && row.status === 'passed'
    )).length,
    failed_total: failures.length + counters.unexpected,
    manifest_sha256: digest(manifestRaw),
    report_sha256: [...reportDigests].sort(),
    nodes: rows,
  };
  if (options.output) {
    await writeFile(resolve(options.output), `${JSON.stringify(summary, null, 2)}\n`);
  }
  console.log(`REQUIRED_TEST_NODE_AUDIT_OK=${accountingPass ? 1 : 0}`);
  if (!accountingPass) {
    console.log('ERROR_CODE=REQUIRED_TEST_NODE_NONPASS');
    process.exitCode = 1;
  }
}

if (process.argv[1]
    && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    const code = /^[A-Z0-9_]+$/.test(String(error?.message ?? ''))
      ? error.message
      : 'REQUIRED_TEST_NODE_AUDIT_FAILED';
    console.log('REQUIRED_TEST_NODE_AUDIT_OK=0');
    console.log(`ERROR_CODE=${code}`);
    process.exitCode = 1;
  });
}
