#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import {
  lstat,
  readFile,
  readdir,
  stat,
  writeFile,
} from 'node:fs/promises';
import {
  isAbsolute,
  relative,
  resolve,
  sep,
} from 'node:path';

import {
  readStrictJsonFile,
} from './strict_json.mjs';
import { collectPinnedActions } from './action_pins.mjs';
import { containsPrivateHomePath } from './evidence_privacy.mjs';

const MAX_PACKAGE_FILES = 512;
const MAX_PACKAGE_BYTES = 512 * 1024 * 1024;
const MAX_JSON_BYTES = 32 * 1024 * 1024;

function parseArgs(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]?.replace(/^--/, '');
    const value = argv[index + 1];
    if (!key || !value) throw new Error('ARGUMENT_INVALID');
    options[key] = value;
  }
  return options;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function safeRelative(value) {
  if (typeof value !== 'string' || !value || value.includes('\\')
      || value.includes('\0') || isAbsolute(value)
      || value.split('/').some(part => (
        part === '' || part === '.' || part === '..'
      ))) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  return value;
}

function safeChild(root, value) {
  safeRelative(value);
  const target = resolve(root, value);
  const rel = relative(root, target);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  return target;
}

async function collectFiles(root, current = root, result = []) {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const target = resolve(current, entry.name);
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink()) throw new Error('PACKAGE_SYMLINK_FORBIDDEN');
    if (metadata.isDirectory()) {
      await collectFiles(root, target, result);
    } else {
      if (!metadata.isFile()) throw new Error('PACKAGE_FILE_TYPE_INVALID');
      result.push(relative(root, target).replaceAll(sep, '/'));
      if (result.length > MAX_PACKAGE_FILES) throw new Error('PACKAGE_FILE_COUNT_EXCEEDED');
    }
  }
  return result;
}

async function requireNonempty(path, failClass) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size === 0) {
    throw new Error(failClass);
  }
}

async function verifyIndex(root, actualFiles, options) {
  const indexPath = resolve(root, 'EVIDENCE_INDEX.json');
  const index = await readStrictJsonFile(indexPath, {
    maxBytes: MAX_JSON_BYTES,
    maxDepth: 32,
    maxNodes: 100_000,
  });
  if (index.schema_version !== 3
      || JSON.stringify(Object.keys(index).sort())
        !== JSON.stringify([
          'manifest', 'runs', 'schema_version', 'subject', 'workflow',
        ])
      || index.subject?.repository !== options.repository
      || index.subject?.pull_request !== Number(options['pull-request'])
      || index.subject?.head_oid?.algorithm !== options['object-format']
      || index.subject?.head_oid?.hex !== options['subject-head']
      || index.subject?.tree_oid?.algorithm !== options['object-format']
      || index.subject?.tree_oid?.hex !== options.tree
      || index.workflow?.runner_kind !== 'github-hosted'
      || index.workflow?.run_id !== options['run-id']
      || index.workflow?.run_attempt !== Number(options['run-attempt'])
      || index.workflow?.workflow_ref !== options['workflow-ref']
      || index.manifest?.path !== 'manifests/required-tests.v3.json'
      || !/^[0-9a-f]{64}$/.test(index.manifest?.sha256 ?? '')
      || index.manifest?.required_total !== 92
      || !Array.isArray(index.runs) || index.runs.length === 0) {
    throw new Error('EVIDENCE_INDEX_INVALID');
  }
  if (sha256(await readFile(
    resolve(root, 'manifests/required-tests.v3.json'),
  )) !== index.manifest.sha256) {
    throw new Error('REQUIRED_MANIFEST_DIGEST_MISMATCH');
  }
  const indexed = [];
  const reportPaths = new Set();
  const contextPaths = new Set();
  for (const run of index.runs) {
    const reportPath = safeRelative(run.raw_result_path);
    const contextPath = safeRelative(run.context_path);
    if (!reportPath.startsWith('reports/')
        || !contextPath.startsWith('contexts/')
        || reportPaths.has(reportPath)
        || contextPaths.has(contextPath)) {
      throw new Error('EVIDENCE_RUN_PATH_INVALID');
    }
    reportPaths.add(reportPath);
    contextPaths.add(contextPath);
    indexed.push(reportPath, contextPath);
  }
  const expected = [
    ...indexed,
    'EVIDENCE_INDEX.json',
    'SHA256SUMS.txt',
    'manifests/evidence-index.schema.json',
    'manifests/action-pins.v1.json',
    'manifests/required-tests.v3.json',
    'source/correction.patch',
    'source/git-ls-tree.txt',
    'source/source.zip',
  ].sort();
  if (JSON.stringify([...actualFiles].sort()) !== JSON.stringify(expected)) {
    throw new Error('EVIDENCE_FILESET_MISMATCH');
  }
  return index;
}

async function verifyChecksums(root, actualFiles) {
  const checksumPath = resolve(root, 'SHA256SUMS.txt');
  const text = await readFile(checksumPath, 'utf8');
  const rows = text.split(/\r?\n/).filter(Boolean);
  if (rows.length === 0) throw new Error('CHECKSUMS_EMPTY');
  const seen = new Set();
  for (const row of rows) {
    const match = row.match(/^([0-9a-f]{64})  (.+)$/);
    if (!match) throw new Error('CHECKSUM_ROW_INVALID');
    const [, expected, name] = match;
    safeRelative(name);
    if (seen.has(name) || name === 'SHA256SUMS.txt') {
      throw new Error('CHECKSUM_TARGET_INVALID');
    }
    seen.add(name);
    const target = safeChild(root, name);
    const metadata = await lstat(target);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error('CHECKSUM_TARGET_INVALID');
    }
    if (sha256(await readFile(target)) !== expected) {
      throw new Error('CHECKSUM_MISMATCH');
    }
  }
  const expected = actualFiles
    .filter(name => name !== 'SHA256SUMS.txt')
    .sort();
  if (JSON.stringify([...seen].sort()) !== JSON.stringify(expected)) {
    throw new Error('CHECKSUM_FILESET_MISMATCH');
  }
  return rows.length;
}

async function verifyContexts(root, index, options) {
  const reportDigests = new Set();
  const contextDigests = new Set();
  const seen = new Set();
  for (const run of index.runs) {
    const reportPath = safeChild(root, run.raw_result_path);
    const contextPath = safeChild(root, run.context_path);
    const reportDigest = sha256(await readFile(reportPath));
    const contextRaw = await readFile(contextPath);
    const contextDigest = sha256(contextRaw);
    if (reportDigest !== run.raw_result_sha256
        || contextDigest !== run.context_sha256
        || reportDigests.has(reportDigest)
        || contextDigests.has(contextDigest)) {
      throw new Error('EVIDENCE_INDEX_DIGEST_MISMATCH');
    }
    reportDigests.add(reportDigest);
    contextDigests.add(contextDigest);
    const context = await readStrictJsonFile(contextPath, {
      maxBytes: 64 * 1024,
    });
    if (context.schema_version !== 2
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
        || context.job_name !== run.job_name
        || context.platform !== run.platform
        || context.runner !== run.runner
        || context.command !== run.command
        || JSON.stringify(context.tool_versions)
          !== JSON.stringify(run.tool_versions)
        || context.started_at !== run.started_at
        || context.finished_at !== run.finished_at
        || Date.parse(context.finished_at) < Date.parse(context.started_at)
        || context.os !== run.os
        || context.arch !== run.arch
        || context.report_sha256 !== reportDigest) {
      throw new Error('CONTEXT_INVALID');
    }
    if (seen.has(reportDigest)) throw new Error('CONTEXT_REPORT_REUSED');
    seen.add(context.report_sha256);
  }
  if (seen.size !== index.runs.length) throw new Error('REPORT_CONTEXT_INCOMPLETE');
  return index.runs.length;
}

async function verifyPrivacy(root, files) {
  const forbidden = [
    /(?:^|["\s])hostname["\s]*:/iu,
  ];
  for (const name of files) {
    if (!/\.(?:json|xml|txt|patch)$/u.test(name)) continue;
    const metadata = await stat(safeChild(root, name));
    if (metadata.size > 16 * 1024 * 1024) continue;
    const text = await readFile(safeChild(root, name), 'utf8');
    if (containsPrivateHomePath(text)
        || forbidden.some(pattern => pattern.test(text))) {
      throw new Error('EVIDENCE_PRIVACY_LEAK');
    }
  }
}

async function verifyActionPins(root) {
  const pins = await readStrictJsonFile(
    resolve(root, 'manifests/action-pins.v1.json'),
    { maxBytes: 64 * 1024 },
  );
  if (pins.schema_version !== 1 || !Array.isArray(pins.actions)
      || pins.actions.length === 0) {
    throw new Error('ACTION_PINS_INVALID');
  }
  const expected = new Map();
  for (const entry of pins.actions) {
    if (typeof entry.repository !== 'string'
        || !/^[0-9a-f]{40}$/.test(entry.resolved_commit_sha ?? '')
        || expected.has(entry.repository)) {
      throw new Error('ACTION_PINS_INVALID');
    }
    expected.set(entry.repository, entry.resolved_commit_sha);
  }
  const sourceZip = resolve(root, 'source/source.zip');
  const listing = spawnSync('unzip', [
    '-p',
    sourceZip,
    '.github/workflows/firstscreen-v2-5.yml',
  ], { encoding: 'utf8' });
  if (listing.status !== 0) throw new Error('WORKFLOW_SOURCE_UNAVAILABLE');
  const observed = collectPinnedActions(listing.stdout);
  if (observed.size !== expected.size
      || [...expected].some(([repository, commit]) => (
        observed.get(repository) !== commit
      ))) {
    throw new Error('ACTION_PIN_MISMATCH');
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  for (const name of [
    'package',
    'zip',
    'detached',
    'repository',
    'subject-head',
    'object-format',
    'tree',
    'pull-request',
    'run-id',
    'run-attempt',
    'workflow-ref',
  ]) {
    if (!options[name]) throw new Error('REQUIRED_INPUT_MISSING');
  }
  if (!['sha1', 'sha256'].includes(options['object-format'])) {
    throw new Error('SUBJECT_IDENTITY_INVALID');
  }
  const oidLength = options['object-format'] === 'sha256' ? 64 : 40;
  if (!new RegExp(`^[0-9a-f]{${oidLength}}$`).test(options['subject-head'])
      || !new RegExp(`^[0-9a-f]{${oidLength}}$`).test(options.tree)
      || !/^[1-9]\d*$/.test(options['pull-request'])
      || !/^[1-9]\d*$/.test(options['run-id'])
      || !/^[1-9]\d*$/.test(options['run-attempt'])) {
    throw new Error('SUBJECT_IDENTITY_INVALID');
  }
  const root = resolve(options.package);
  const rootMetadata = await lstat(root);
  if (!rootMetadata.isDirectory() || rootMetadata.isSymbolicLink()) {
    throw new Error('PACKAGE_ROOT_INVALID');
  }
  const files = await collectFiles(root);
  let totalBytes = 0;
  for (const name of files) totalBytes += (await stat(safeChild(root, name))).size;
  if (totalBytes > MAX_PACKAGE_BYTES) throw new Error('PACKAGE_TOO_LARGE');

  const index = await verifyIndex(root, files, options);
  const checksumCount = await verifyChecksums(root, files);
  for (const [path, failClass] of [
    ['source/source.zip', 'FULL_SOURCE_ARCHIVE_MISSING'],
    ['source/git-ls-tree.txt', 'TREE_MANIFEST_MISSING'],
    ['source/correction.patch', 'CORRECTION_PATCH_MISSING'],
    ['reports/required-node-audit.json', 'REQUIRED_NODE_REPORT_MISSING'],
  ]) {
    await requireNonempty(resolve(root, path), failClass);
  }
  const contextCount = await verifyContexts(root, index, options);
  await verifyPrivacy(root, files);
  await verifyActionPins(root);

  const zip = resolve(options.zip);
  const detachedText = (await readFile(resolve(options.detached), 'utf8')).trim();
  const detachedMatch = detachedText.match(/^([0-9a-f]{64})(?:\s+.+)?$/);
  if (!detachedMatch) throw new Error('DETACHED_DIGEST_INVALID');
  const zipDigest = sha256(await readFile(zip));
  if (zipDigest !== detachedMatch[1]) throw new Error('DETACHED_DIGEST_MISMATCH');
  const result = {
    schema_version: 3,
    subject_head: options['subject-head'],
    tree_oid: {
      algorithm: options['object-format'],
      hex: options.tree,
    },
    checksum_count: checksumCount,
    context_count: contextCount,
    zip_sha256: zipDigest,
    detached_digest_match: true,
    internal_checksums_verified: true,
  };
  if (options.output) {
    await writeFile(resolve(options.output), `${JSON.stringify(result, null, 2)}\n`);
  }
  console.log('FIRSTSCREEN_EVIDENCE_VERIFY_OK=1');
}

main().catch(error => {
  console.log('FIRSTSCREEN_EVIDENCE_VERIFY_OK=0');
  console.log(`ERROR_CODE=${error.message}`);
  process.exitCode = 1;
});
