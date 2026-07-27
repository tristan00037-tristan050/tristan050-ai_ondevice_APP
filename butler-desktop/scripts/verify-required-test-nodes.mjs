import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

function args(argv) {
  const result = { playwright: [] };
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    if (key === 'playwright') result.playwright.push(value);
    else result[key] = value;
  }
  return result;
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
if (manifest.schema_version !== 1 || !Array.isArray(manifest.tests)) {
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
  nodes: rows,
};
if (options.output) {
  await writeFile(resolve(options.output), `${JSON.stringify(summary, null, 2)}\n`);
}
const pass = summary.missing === 0
  && summary.skipped === 0
  && summary.deselected === 0
  && summary.xfail === 0
  && summary.failed === 0;
console.log(`REQUIRED_TEST_NODE_AUDIT=${pass ? 'PASS' : 'FAIL'}`);
console.log(`REQUIRED_TEST_NODES_MISSING=${summary.missing}`);
console.log(`REQUIRED_TEST_NODES_SKIPPED=${summary.skipped}`);
console.log(`REQUIRED_TEST_NODES_DESELECTED=${summary.deselected}`);
console.log(`REQUIRED_TEST_NODES_XFAIL=${summary.xfail}`);
console.log(`REQUIRED_TEST_NODES_FAILED=${summary.failed}`);
if (!pass) process.exitCode = 1;
