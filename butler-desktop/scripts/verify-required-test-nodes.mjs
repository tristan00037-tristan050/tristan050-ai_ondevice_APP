import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import { isAbsolute, posix, relative, resolve } from 'node:path';

const MAX_REPORT_BYTES = 32 * 1024 * 1024;
const repositoryRoot = resolve(import.meta.dirname, '..', '..');

function args(argv) {
  const result = {
    playwright: [],
    pytest: [],
    node: [],
    context: [],
  };
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    if (['playwright', 'pytest', 'node', 'context'].includes(key)) {
      result[key].push(value);
    }
    else result[key] = value;
  }
  return result;
}

async function readRegular(path, maximum = MAX_REPORT_BYTES) {
  const absolute = resolve(path);
  const info = await lstat(absolute);
  if (!info.isFile() || info.isSymbolicLink() || info.size > maximum) {
    throw new Error('REPORT_FILE_INVALID');
  }
  return readFile(absolute, 'utf8');
}

function assertNoDuplicateJsonKeys(text) {
  let index = 0;
  const whitespace = () => {
    while (/\s/u.test(text[index] ?? '')) index += 1;
  };
  const stringToken = () => {
    if (text[index] !== '"') throw new Error('STRICT_JSON_INVALID');
    const start = index;
    index += 1;
    while (index < text.length) {
      if (text[index] === '\\') {
        index += 2;
        continue;
      }
      if (text[index] === '"') {
        index += 1;
        return JSON.parse(text.slice(start, index));
      }
      index += 1;
    }
    throw new Error('STRICT_JSON_INVALID');
  };
  const value = () => {
    whitespace();
    if (text[index] === '{') {
      index += 1;
      const keys = new Set();
      whitespace();
      if (text[index] === '}') {
        index += 1;
        return;
      }
      while (index < text.length) {
        whitespace();
        const key = stringToken();
        if (keys.has(key)) throw new Error('JSON_DUPLICATE_KEY');
        keys.add(key);
        whitespace();
        if (text[index] !== ':') throw new Error('STRICT_JSON_INVALID');
        index += 1;
        value();
        whitespace();
        if (text[index] === '}') {
          index += 1;
          return;
        }
        if (text[index] !== ',') throw new Error('STRICT_JSON_INVALID');
        index += 1;
      }
    } else if (text[index] === '[') {
      index += 1;
      whitespace();
      if (text[index] === ']') {
        index += 1;
        return;
      }
      while (index < text.length) {
        value();
        whitespace();
        if (text[index] === ']') {
          index += 1;
          return;
        }
        if (text[index] !== ',') throw new Error('STRICT_JSON_INVALID');
        index += 1;
      }
    } else if (text[index] === '"') {
      stringToken();
    } else {
      const match = text.slice(index).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/u);
      if (!match) throw new Error('STRICT_JSON_INVALID');
      index += match[0].length;
    }
  };
  value();
  whitespace();
  if (index !== text.length) throw new Error('STRICT_JSON_INVALID');
}

function strictJson(text) {
  assertNoDuplicateJsonKeys(text);
  return JSON.parse(text);
}

function decodeXml(value) {
  return String(value)
    .replaceAll('&quot;', '"')
    .replaceAll('&apos;', "'")
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&amp;', '&');
}

function xmlAttribute(source, name) {
  const match = source.match(new RegExp(`\\b${name}="([^"]*)"`));
  return match ? decodeXml(match[1]) : '';
}

function collectPytest(xml) {
  const nodes = [];
  const pattern = /<testcase\b([^>]*)(?:\/>|>([\s\S]*?)<\/testcase>)/g;
  for (const match of xml.matchAll(pattern)) {
    const attributes = match[1] ?? '';
    const body = match[2] ?? '';
    const className = xmlAttribute(attributes, 'classname');
    const title = xmlAttribute(attributes, 'name');
    if (!className || !title) continue;
    let status = 'passed';
    if (/<(?:failure|error)\b/.test(body)) status = 'failed';
    else if (/<skipped\b/.test(body)) status = 'skipped';
    nodes.push({
      runner: 'pytest',
      file: `${className.replaceAll('.', '/')}.py`,
      title,
      status,
    });
  }
  return nodes;
}

function collectNode(report) {
  if (report?.schema_version !== 1 || !Array.isArray(report.nodes)) {
    throw new Error('NODE_REPORT_INVALID');
  }
  return report.nodes.map(node => ({
    runner: 'node',
    file: normalizedFile(node.file),
    title: node.title,
    status: node.status,
  }));
}

function requiredFile(value) {
  const file = String(value ?? '');
  if (
    !file
    || file.includes('\\')
    || isAbsolute(file)
    || file.split('/').some(segment => !segment || segment === '.' || segment === '..')
    || posix.normalize(file) !== file
  ) {
    throw new Error('REQUIRED_PATH_INVALID');
  }
  return file;
}

function normalizedFile(value) {
  const file = String(value ?? '').replaceAll('\\', '/');
  if (isAbsolute(file)) {
    const local = relative(repositoryRoot, resolve(file)).replaceAll('\\', '/');
    if (!local.startsWith('../')) return local;
  }
  return file.replace(/^\.\//u, '');
}

function collectVitest(report) {
  const nodes = [];
  for (const file of report.testResults ?? []) {
    for (const assertion of file.assertionResults ?? []) {
      nodes.push({
        runner: 'vitest',
        file: normalizedFile(file.name),
        title: assertion.title,
        status: assertion.status,
      });
    }
  }
  return nodes;
}

function collectPlaywrightSuite(suite, inheritedFile, nodes) {
  const file = normalizedFile(suite.file ?? inheritedFile);
  for (const spec of suite.specs ?? []) {
    const tests = spec.tests ?? [];
    const results = tests.flatMap(test => test.results ?? []);
    const expected = tests.every(test => (test.expectedStatus ?? 'passed') === 'passed');
    let status = 'missing';
    if (!expected) status = 'xfail';
    else if (results.some(result => result.status === 'failed'
        || result.status === 'timedOut'
        || result.status === 'interrupted')) status = 'failed';
    else if (results.some(result => result.status === 'passed')) status = 'passed';
    else if (results.some(result => result.status === 'skipped')) status = 'skipped';
    nodes.push({
      runner: 'playwright',
      file,
      title: spec.title,
      status,
    });
  }
  for (const child of suite.suites ?? []) {
    collectPlaywrightSuite(child, file, nodes);
  }
}

function collectPlaywright(report) {
  const nodes = [];
  for (const suite of report.suites ?? []) {
    collectPlaywrightSuite(suite, '', nodes);
  }
  return nodes;
}

function digest(text) {
  return createHash('sha256').update(text).digest('hex');
}

const options = args(process.argv.slice(2));
const objectFormat = execFileSync('git', ['rev-parse', '--show-object-format'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
const oidLength = objectFormat === 'sha256' ? 64 : objectFormat === 'sha1' ? 40 : 0;
const oidPattern = new RegExp(`^[0-9a-f]{${oidLength}}$`);
const checkoutHead = execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
const checkoutTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
if (!options.manifest || !options.vitest || !options.playwright.length
    || !options.head || !oidPattern.test(options.head)) {
  throw new Error('REQUIRED_INPUT_MISSING');
}
const manifestText = await readRegular(options.manifest, 1024 * 1024);
const manifest = strictJson(manifestText);
if (![1, 2].includes(manifest.schema_version) || !Array.isArray(manifest.tests)) {
  throw new Error('MANIFEST_INVALID');
}
if (checkoutHead !== options.head) throw new Error('CHECKOUT_HEAD_MISMATCH');
const requiredIds = new Set();
const requiredTriples = new Set();
for (const test of manifest.tests) {
  if (typeof test.id !== 'string' || requiredIds.has(test.id)) {
    throw new Error('REQUIRED_ID_DUPLICATE');
  }
  requiredIds.add(test.id);
  test.file = requiredFile(test.file);
  const triple = `${test.runner}\0${test.file}\0${test.title}`;
  if (requiredTriples.has(triple)) throw new Error('REQUIRED_NODE_DUPLICATE');
  requiredTriples.add(triple);
}

const vitestText = await readRegular(options.vitest);
const actual = collectVitest(strictJson(vitestText));
const playwrightDigests = [];
for (const path of options.playwright) {
  const text = await readRegular(path);
  playwrightDigests.push(digest(text));
  actual.push(...collectPlaywright(strictJson(text)));
}
const pytestDigests = [];
for (const path of options.pytest) {
  const text = await readRegular(path);
  pytestDigests.push(digest(text));
  actual.push(...collectPytest(text));
}
const nodeDigests = [];
for (const path of options.node) {
  const text = await readRegular(path);
  nodeDigests.push(digest(text));
  actual.push(...collectNode(strictJson(text)));
}
const actualIdentities = new Set();
for (const node of actual) {
  node.file = normalizedFile(node.file);
  if (
    ['vitest', 'playwright'].includes(node.runner)
    && !node.file.startsWith('butler-desktop/')
  ) {
    node.file = `butler-desktop/${node.file}`;
  }
  const identity = `${node.runner}\0${node.file}\0${node.title}`;
  if (actualIdentities.has(identity)) throw new Error('ACTUAL_NODE_DUPLICATE');
  actualIdentities.add(identity);
}

const reportDigests = new Set([
  digest(vitestText),
  ...playwrightDigests,
  ...pytestDigests,
  ...nodeDigests,
]);
let headMismatch = 0;
let contextMissing = 0;
let artifactDigestMismatch = 0;
const contextualizedReports = new Set();
if (manifest.schema_version === 2 && options.context.length === 0) {
  contextMissing = 1;
}
for (const path of options.context) {
  const context = strictJson(await readRegular(path, 1024 * 1024));
  if (context?.schema_version !== 1
      || context.subject_pr_head !== options.head
      || context.execution_commit !== options.head
      || !/^\d+$/.test(context.workflow_run_id ?? '')
      || context.tree_oid?.algorithm !== objectFormat
      || !oidPattern.test(context.tree_oid?.hex ?? '')
      || context.tree_oid.hex !== checkoutTree) {
    headMismatch += 1;
  }
  if (!reportDigests.has(context.report_sha256)) {
    artifactDigestMismatch += 1;
  } else {
    contextualizedReports.add(context.report_sha256);
  }
}
if (manifest.schema_version === 2) {
  contextMissing += [...reportDigests]
    .filter(value => !contextualizedReports.has(value)).length;
}

const required = manifest.tests.filter(test => test.required === true);
const consumedActual = new Set();
const rows = required.map(test => {
  const matches = actual.map((node, index) => ({ node, index })).filter(({ node }) =>
    node.runner === test.runner
    && normalizedFile(node.file) === test.file
    && node.title === test.title);
  const statuses = matches.map(match => match.node.status);
  if (matches.length === 1) {
    if (consumedActual.has(matches[0].index)) throw new Error('ACTUAL_NODE_REUSED');
    consumedActual.add(matches[0].index);
  }
  return {
    id: test.id,
    executed: matches.length,
    status: statuses.includes('failed')
        ? 'failed'
        : statuses.includes('xfail')
          ? 'xfail'
          : statuses.includes('skipped')
            ? 'skipped'
            : statuses.includes('passed')
              ? 'passed'
              : 'missing',
  };
});

const summary = {
  schema_version: 1,
  suite: manifest.suite,
  pr_head: options.head,
  required_total: required.length,
  executed_total: rows.filter(row => row.executed > 0).length,
  missing: rows.filter(row => row.status === 'missing').length,
  skipped: rows.filter(row => row.status === 'skipped').length,
  deselected: rows.filter(row => row.executed === 0).length,
  xfail: rows.filter(row => row.status === 'xfail').length,
  failed: rows.filter(row => row.status === 'failed').length,
  manifest_sha256: digest(manifestText),
  vitest_report_sha256: digest(vitestText),
  playwright_report_sha256: playwrightDigests,
  pytest_report_sha256: pytestDigests,
  node_report_sha256: nodeDigests,
  head_mismatch: headMismatch,
  tree_mismatch: headMismatch,
  duplicate_required: 0,
  duplicate_actual: 0,
  reused_actual: 0,
  context_missing: contextMissing,
  artifact_digest_mismatch: artifactDigestMismatch,
  nodes: rows,
};
if (options.output) {
  await writeFile(resolve(options.output), `${JSON.stringify(summary, null, 2)}\n`);
}
const pass = summary.missing === 0
  && summary.skipped === 0
  && summary.deselected === 0
  && summary.xfail === 0
  && summary.failed === 0
  && summary.head_mismatch === 0
  && summary.tree_mismatch === 0
  && summary.context_missing === 0
  && summary.artifact_digest_mismatch === 0;
console.log(`REQUIRED_TEST_NODE_AUDIT=${pass ? 'PASS' : 'FAIL'}`);
console.log(`REQUIRED_TEST_NODES_MISSING=${summary.missing}`);
console.log(`REQUIRED_TEST_NODES_SKIPPED=${summary.skipped}`);
console.log(`REQUIRED_TEST_NODES_DESELECTED=${summary.deselected}`);
console.log(`REQUIRED_TEST_NODES_XFAIL=${summary.xfail}`);
console.log(`REQUIRED_TEST_NODES_FAILED=${summary.failed}`);
console.log(`REQUIRED_TEST_HEAD_MISMATCH=${summary.head_mismatch}`);
console.log(`REQUIRED_TEST_TREE_MISMATCH=${summary.tree_mismatch}`);
console.log(`REQUIRED_TEST_CONTEXT_MISSING=${summary.context_missing}`);
console.log(`REQUIRED_TEST_ARTIFACT_DIGEST_MISMATCH=${summary.artifact_digest_mismatch}`);
if (!pass) process.exitCode = 1;
