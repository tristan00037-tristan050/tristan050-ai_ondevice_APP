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
const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const startedAt = Date.parse(options['started-at']);
const finishedAt = Date.parse(options['finished-at']);
if (!rfc3339.test(options['started-at'])
    || !rfc3339.test(options['finished-at'])
    || !Number.isFinite(startedAt) || !Number.isFinite(finishedAt)
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
const repository = options.repository ?? process.env.GITHUB_REPOSITORY;
const eventName = options['event-name'] ?? process.env.GITHUB_EVENT_NAME;
const prNumberText = options['pr-number'] ?? process.env.PR_NUMBER;
const workflowRef = options['workflow-ref'] ?? process.env.GITHUB_WORKFLOW_REF;
const jobName = options['job-name'] ?? process.env.GITHUB_JOB;
const platform = options.platform ?? (
  options.os === 'Windows' ? 'windows-2025'
    : options.os === 'macOS' ? 'macos-15'
      : options.os === 'Linux' ? 'ubuntu' : ''
);
if (typeof repository !== 'string' || !/^[^/\s]+\/[^/\s]+$/.test(repository)
    || !['pull_request', 'merge_group', 'push', 'workflow_dispatch'].includes(eventName)
    || !/^(?:0|[1-9]\d*)$/.test(prNumberText ?? '')
    || typeof workflowRef !== 'string' || workflowRef.length === 0
    || typeof jobName !== 'string' || jobName.length === 0
    || !['ubuntu', 'windows-2025', 'macos-15'].includes(platform)) {
  throw new Error('CONTEXT_WORKFLOW_IDENTITY_INVALID');
}
const context = {
  schema_version: 2,
  repository,
  event_name: eventName,
  pr_number: Number(prNumberText),
  suite: options.suite,
  subject_head: options['subject-head'],
  execution_commit: options['execution-commit'],
  tree: options.tree,
  object_format: options['object-format'],
  run_id: options['run-id'],
  run_attempt: Number(options['run-attempt']),
  workflow_ref: workflowRef,
  job_name: jobName,
  runner: options.runner,
  platform,
  command: options.command,
  report_path: options.report.replaceAll('\\', '/'),
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
