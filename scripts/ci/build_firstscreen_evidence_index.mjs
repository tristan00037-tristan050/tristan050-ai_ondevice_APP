#!/usr/bin/env node
import { createHash } from 'node:crypto';
import {
  lstat,
  readFile,
  readdir,
  writeFile,
} from 'node:fs/promises';
import { relative, resolve, sep } from 'node:path';

import { readStrictJsonFile } from './strict_json.mjs';

function args(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    result[key] = value;
  }
  return result;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function files(root, current = root, result = []) {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const target = resolve(current, entry.name);
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink()) throw new Error('SYMLINK_FORBIDDEN');
    if (metadata.isDirectory()) await files(root, target, result);
    else if (metadata.isFile()) {
      result.push(relative(root, target).replaceAll(sep, '/'));
    } else throw new Error('FILE_TYPE_FORBIDDEN');
  }
  return result;
}

function requireOid(value, algorithm) {
  const length = algorithm === 'sha256' ? 64 : algorithm === 'sha1' ? 40 : 0;
  if (!length || !new RegExp(`^[0-9a-f]{${length}}$`).test(value)) {
    throw new Error('SUBJECT_OID_INVALID');
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
  'report_sha256',
  'started_at',
  'finished_at',
  'tool_versions',
]);
const RUNTIME_BY_PLATFORM = {
  ubuntu: { os: 'Linux', arch: 'X64' },
  'windows-2025': { os: 'Windows', arch: 'X64' },
  'macos-15': { os: 'macOS', arch: 'ARM64' },
};

const options = args(process.argv.slice(2));
for (const name of [
  'package',
  'repository',
  'pull-request',
  'subject-head',
  'object-format',
  'tree',
  'run-id',
  'run-attempt',
  'workflow-ref',
]) {
  if (!options[name]) throw new Error('REQUIRED_INPUT_MISSING');
}
requireOid(options['subject-head'], options['object-format']);
requireOid(options.tree, options['object-format']);
if (!/^[1-9]\d*$/.test(options['pull-request'])
    || !/^[1-9]\d*$/.test(options['run-id'])
    || !/^[1-9]\d*$/.test(options['run-attempt'])) {
  throw new Error('WORKFLOW_IDENTITY_INVALID');
}

const root = resolve(options.package);
const names = (await files(root)).sort();
if (names.some(name => ['EVIDENCE_INDEX.json', 'SHA256SUMS.txt'].includes(name))) {
  throw new Error('INDEX_OUTPUT_ALREADY_EXISTS');
}
const reports = new Map();
for (const name of names.filter(value => value.startsWith('reports/'))) {
  const digest = sha256(await readFile(resolve(root, name)));
  if (reports.has(digest)) throw new Error('REPORT_DIGEST_DUPLICATE');
  reports.set(digest, name);
}
const contextNames = names.filter(value => (
  value.startsWith('contexts/') && value.endsWith('.json')
));
if (reports.size === 0 || contextNames.length !== reports.size) {
  throw new Error('REPORT_CONTEXT_CARDINALITY_INVALID');
}

const usedReports = new Set();
const runs = [];
for (const contextPath of contextNames) {
  const absolute = resolve(root, contextPath);
  const rawContext = await readFile(absolute);
  const context = await readStrictJsonFile(absolute, { maxBytes: 64 * 1024 });
  const reportPath = reports.get(context.report_sha256);
  if (!reportPath || usedReports.has(reportPath)) {
    throw new Error('REPORT_CONTEXT_BINDING_INVALID');
  }
  if (context.schema_version !== 2
      || Object.keys(context).length !== CONTEXT_KEYS.size
      || Object.keys(context).some(key => !CONTEXT_KEYS.has(key))
      || context.repository !== options.repository
      || context.event_name !== 'pull_request'
      || context.pr_number !== Number(options['pull-request'])
      || context.subject_head !== options['subject-head']
      || context.execution_commit !== options['subject-head']
      || context.tree !== options.tree
      || context.object_format !== options['object-format']
      || context.run_id !== options['run-id']
      || context.run_attempt !== Number(options['run-attempt'])
      || context.workflow_ref !== options['workflow-ref']
      || typeof context.job_name !== 'string'
      || typeof context.runner !== 'string'
      || !Object.hasOwn(RUNTIME_BY_PLATFORM, context.platform)
      || context.report_path !== reportPath
      || typeof context.command !== 'string'
      || typeof context.tool_versions !== 'object'
      || context.tool_versions === null
      || Array.isArray(context.tool_versions)
      || !Number.isFinite(Date.parse(context.started_at))
      || !Number.isFinite(Date.parse(context.finished_at))
      || Date.parse(context.finished_at) < Date.parse(context.started_at)
      || typeof context.report_sha256 !== 'string') {
    throw new Error('CONTEXT_CONTRACT_INVALID');
  }
  const runtime = RUNTIME_BY_PLATFORM[context.platform];
  usedReports.add(reportPath);
  runs.push({
    job_name: context.job_name,
    runner: context.runner,
    platform: context.platform,
    command: context.command,
    tool_versions: context.tool_versions,
    exit_code: 0,
    started_at: context.started_at,
    finished_at: context.finished_at,
    os: runtime.os,
    arch: runtime.arch,
    execution_oid: {
      algorithm: options['object-format'],
      hex: options['subject-head'],
    },
    tree_oid: {
      algorithm: options['object-format'],
      hex: options.tree,
    },
    raw_result_path: reportPath,
    raw_result_sha256: context.report_sha256,
    context_path: contextPath,
    context_sha256: sha256(rawContext),
  });
}
if (usedReports.size !== reports.size) throw new Error('REPORT_CONTEXT_INCOMPLETE');
runs.sort((left, right) => (
  left.raw_result_path.localeCompare(right.raw_result_path)
));

const index = {
  schema_version: 3,
  subject: {
    repository: options.repository,
    pull_request: Number(options['pull-request']),
    head_oid: {
      algorithm: options['object-format'],
      hex: options['subject-head'],
    },
    tree_oid: {
      algorithm: options['object-format'],
      hex: options.tree,
    },
  },
  workflow: {
    runner_kind: 'github-hosted',
    run_id: options['run-id'],
    run_attempt: Number(options['run-attempt']),
    workflow_ref: options['workflow-ref'],
  },
  manifest: {
    path: 'manifests/required-tests.v3.json',
    sha256: sha256(
      await readFile(resolve(root, 'manifests/required-tests.v3.json')),
    ),
    required_total: 92,
  },
  runs,
};
await writeFile(
  resolve(root, 'EVIDENCE_INDEX.json'),
  `${JSON.stringify(index, null, 2)}\n`,
  { flag: 'wx' },
);
console.log('FIRSTSCREEN_EVIDENCE_INDEX_OK=1');
