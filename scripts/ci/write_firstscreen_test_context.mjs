#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

import { parseStrictJson } from './strict_json.mjs';

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
  'object-format',
  'run-id',
  'run-attempt',
  'suite',
  'runner',
  'command',
  'tool-versions',
  'started-at',
  'finished-at',
  'os',
  'arch',
]) {
  if (!options[key]) throw new Error(`REQUIRED_${key.toUpperCase()}_MISSING`);
}
const oidLength = options['object-format'] === 'sha256'
  ? 64
  : options['object-format'] === 'sha1'
    ? 40
    : 0;
const oid = new RegExp(`^[0-9a-f]{${oidLength}}$`);
if (!oidLength
    || !oid.test(options['subject-head'])
    || !oid.test(options['execution-commit'])
    || !oid.test(options.tree)
    || !/^[1-9]\d*$/.test(options['run-id'])
    || !/^[1-9]\d*$/.test(options['run-attempt'])) {
  throw new Error('CONTEXT_IDENTITY_INVALID');
}
const startedAt = Date.parse(options['started-at']);
const finishedAt = Date.parse(options['finished-at']);
if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)
    || finishedAt < startedAt) {
  throw new Error('CONTEXT_TIME_INVALID');
}
const toolVersions = parseStrictJson(
  Buffer.from(options['tool-versions'], 'utf8'),
  { maxBytes: 4096, maxDepth: 4, maxNodes: 32 },
);
if (Object.keys(toolVersions).length === 0
    || Object.values(toolVersions).some(value => (
      typeof value !== 'string' || value.length === 0 || value.length > 256
    ))) {
  throw new Error('CONTEXT_TOOL_VERSIONS_INVALID');
}
const report = await readFile(resolve(options.report));
const context = {
  schema_version: 1,
  suite: options.suite,
  subject_pr_head: options['subject-head'],
  execution_commit: options['execution-commit'],
  tree_oid: {
    algorithm: options['object-format'],
    hex: options.tree,
  },
  workflow_run_id: options['run-id'],
  workflow_run_attempt: Number(options['run-attempt']),
  runner: options.runner,
  command: options.command,
  tool_versions: toolVersions,
  started_at: options['started-at'],
  finished_at: options['finished-at'],
  os: options.os,
  arch: options.arch,
  report_sha256: createHash('sha256').update(report).digest('hex'),
};
await writeFile(
  resolve(options.output),
  `${JSON.stringify(context, null, 2)}\n`,
);
console.log('FIRSTSCREEN_TEST_CONTEXT_OK=1');
