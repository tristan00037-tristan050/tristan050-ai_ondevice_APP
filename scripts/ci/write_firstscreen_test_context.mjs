#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const options = {};
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index]?.replace(/^--/, '');
  const value = process.argv[index + 1];
  if (!key || !value) throw new Error('ARGUMENT_INVALID');
  options[key] = value;
}
for (const key of [
  'report',
  'output',
  'subject-head',
  'execution-commit',
  'tree',
  'run-id',
  'suite',
]) {
  if (!options[key]) throw new Error(`REQUIRED_${key.toUpperCase()}_MISSING`);
}
if (!/^[0-9a-f]{40}$/.test(options['subject-head'])
    || !/^[0-9a-f]{40}$/.test(options['execution-commit'])
    || !/^[0-9a-f]{40}$/.test(options.tree)
    || !/^\d+$/.test(options['run-id'])) {
  throw new Error('CONTEXT_IDENTITY_INVALID');
}
const report = await readFile(resolve(options.report));
const context = {
  schema_version: 1,
  suite: options.suite,
  subject_pr_head: options['subject-head'],
  execution_commit: options['execution-commit'],
  tree_oid: {
    algorithm: 'sha1',
    hex: options.tree,
  },
  workflow_run_id: options['run-id'],
  report_sha256: createHash('sha256').update(report).digest('hex'),
};
await writeFile(
  resolve(options.output),
  `${JSON.stringify(context, null, 2)}\n`,
);
console.log('FIRSTSCREEN_TEST_CONTEXT=PASS');

