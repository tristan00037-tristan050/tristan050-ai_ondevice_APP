#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import { arch, platform } from 'node:os';
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
const repositoryRoot = resolve(import.meta.dirname, '..', '..');
const objectFormat = execFileSync('git', ['rev-parse', '--show-object-format'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
const oidLength = objectFormat === 'sha256' ? 64 : objectFormat === 'sha1' ? 40 : 0;
const oidPattern = new RegExp(`^[0-9a-f]{${oidLength}}$`);
const actualHead = execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
const actualTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
  cwd: repositoryRoot,
  encoding: 'utf8',
}).trim();
if (!oidPattern.test(options['subject-head'])
    || !oidPattern.test(options['execution-commit'])
    || !oidPattern.test(options.tree)
    || options['subject-head'] !== actualHead
    || options['execution-commit'] !== actualHead
    || options.tree !== actualTree
    || !/^\d+$/.test(options['run-id'])) {
  throw new Error('CONTEXT_IDENTITY_INVALID');
}
const reportPath = resolve(options.report);
const reportInfo = await lstat(reportPath);
if (!reportInfo.isFile() || reportInfo.isSymbolicLink() || reportInfo.size > 32 * 1024 * 1024) {
  throw new Error('CONTEXT_REPORT_INVALID');
}
const report = await readFile(reportPath);
const now = new Date().toISOString();
const context = {
  schema_version: 1,
  suite: options.suite,
  command: options.command ?? options.suite,
  exit_code: 0,
  subject_pr_head: options['subject-head'],
  execution_commit: options['execution-commit'],
  tree_oid: {
    algorithm: objectFormat,
    hex: options.tree,
  },
  workflow_run_id: options['run-id'],
  workflow_run_attempt: Number(process.env.GITHUB_RUN_ATTEMPT ?? '1'),
  workflow_ref: process.env.GITHUB_WORKFLOW_REF ?? 'local/not-authoritative',
  runner_kind: process.env.GITHUB_ACTIONS === 'true' ? 'github-hosted' : 'local',
  os: platform(),
  arch: arch(),
  started_at: now,
  finished_at: now,
  tool_versions: { node: process.version },
  report_sha256: createHash('sha256').update(report).digest('hex'),
};
await writeFile(
  resolve(options.output),
  `${JSON.stringify(context, null, 2)}\n`,
);
console.log('FIRSTSCREEN_TEST_CONTEXT=PASS');
