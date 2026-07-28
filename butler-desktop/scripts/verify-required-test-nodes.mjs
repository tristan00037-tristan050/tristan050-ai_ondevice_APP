import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

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

function normalizedFile(value) {
  return String(value ?? '').replaceAll('\\', '/');
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
if (!options.manifest || !options.vitest || !options.playwright.length
    || !options.head || !/^[0-9a-f]{40}$/.test(options.head)) {
  throw new Error('REQUIRED_INPUT_MISSING');
}
const manifestText = await readFile(resolve(options.manifest), 'utf8');
const manifest = JSON.parse(manifestText);
if (![1, 2].includes(manifest.schema_version) || !Array.isArray(manifest.tests)) {
  throw new Error('MANIFEST_INVALID');
}

const vitestText = await readFile(resolve(options.vitest), 'utf8');
const actual = collectVitest(JSON.parse(vitestText));
const playwrightDigests = [];
for (const path of options.playwright) {
  const text = await readFile(resolve(path), 'utf8');
  playwrightDigests.push(digest(text));
  actual.push(...collectPlaywright(JSON.parse(text)));
}
const pytestDigests = [];
for (const path of options.pytest) {
  const text = await readFile(resolve(path), 'utf8');
  pytestDigests.push(digest(text));
  actual.push(...collectPytest(text));
}
const nodeDigests = [];
for (const path of options.node) {
  const text = await readFile(resolve(path), 'utf8');
  nodeDigests.push(digest(text));
  actual.push(...collectNode(JSON.parse(text)));
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
  const context = JSON.parse(await readFile(resolve(path), 'utf8'));
  if (context?.schema_version !== 1
      || context.subject_pr_head !== options.head
      || !/^[0-9a-f]{40}$/.test(context.execution_commit ?? '')
      || !/^\d+$/.test(context.workflow_run_id ?? '')
      || context.tree_oid?.algorithm !== 'sha1'
      || !/^[0-9a-f]{40}$/.test(context.tree_oid?.hex ?? '')) {
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
const rows = required.map(test => {
  const matches = actual.filter(node =>
    node.runner === test.runner
    && (
      normalizedFile(node.file).endsWith(normalizedFile(test.file))
      || (
        !normalizedFile(node.file).includes('/')
        && normalizedFile(test.file).endsWith(`/${normalizedFile(node.file)}`)
      )
    )
    && node.title === test.title);
  const statuses = matches.map(match => match.status);
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
  && summary.context_missing === 0
  && summary.artifact_digest_mismatch === 0;
console.log(`REQUIRED_TEST_NODE_AUDIT=${pass ? 'PASS' : 'FAIL'}`);
console.log(`REQUIRED_TEST_NODES_MISSING=${summary.missing}`);
console.log(`REQUIRED_TEST_NODES_SKIPPED=${summary.skipped}`);
console.log(`REQUIRED_TEST_NODES_DESELECTED=${summary.deselected}`);
console.log(`REQUIRED_TEST_NODES_XFAIL=${summary.xfail}`);
console.log(`REQUIRED_TEST_NODES_FAILED=${summary.failed}`);
console.log(`REQUIRED_TEST_HEAD_MISMATCH=${summary.head_mismatch}`);
console.log(`REQUIRED_TEST_CONTEXT_MISSING=${summary.context_missing}`);
console.log(`REQUIRED_TEST_ARTIFACT_DIGEST_MISMATCH=${summary.artifact_digest_mismatch}`);
if (!pass) process.exitCode = 1;
