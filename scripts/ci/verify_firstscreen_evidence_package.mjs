#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { lstat, readFile, readdir, writeFile } from 'node:fs/promises';
import { isAbsolute, relative, resolve, sep } from 'node:path';

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

function safeChild(root, value) {
  if (!value || isAbsolute(value) || value.includes('\0')
      || value.includes('\\') || value.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  const target = resolve(root, value);
  const rel = relative(root, target);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  return target;
}

function rejectDuplicateKeys(text) {
  let index = 0;
  function whitespace() {
    while (/\s/.test(text[index] ?? '')) index += 1;
  }
  function stringToken() {
    if (text[index] !== '"') throw new Error('JSON_STRING_EXPECTED');
    const start = index;
    index += 1;
    while (index < text.length) {
      if (text[index] === '\\') {
        index += 2;
      } else if (text[index] === '"') {
        index += 1;
        return JSON.parse(text.slice(start, index));
      } else {
        index += 1;
      }
    }
    throw new Error('JSON_STRING_UNTERMINATED');
  }
  function value() {
    whitespace();
    if (text[index] === '{') {
      index += 1;
      whitespace();
      const keys = new Set();
      while (text[index] !== '}') {
        const key = stringToken();
        if (keys.has(key)) throw new Error('JSON_DUPLICATE_KEY');
        keys.add(key);
        whitespace();
        if (text[index++] !== ':') throw new Error('JSON_COLON_EXPECTED');
        value();
        whitespace();
        if (text[index] === ',') {
          index += 1;
          whitespace();
        } else if (text[index] !== '}') {
          throw new Error('JSON_OBJECT_INVALID');
        }
      }
      index += 1;
      return;
    }
    if (text[index] === '[') {
      index += 1;
      whitespace();
      while (text[index] !== ']') {
        value();
        whitespace();
        if (text[index] === ',') {
          index += 1;
          whitespace();
        } else if (text[index] !== ']') {
          throw new Error('JSON_ARRAY_INVALID');
        }
      }
      index += 1;
      return;
    }
    if (text[index] === '"') {
      stringToken();
      return;
    }
    const match = text.slice(index).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
    if (!match) throw new Error('JSON_VALUE_INVALID');
    index += match[0].length;
  }
  value();
  whitespace();
  if (index !== text.length) throw new Error('JSON_TRAILING_DATA');
}

async function strictJson(path) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > MAX_JSON_BYTES) {
    throw new Error('JSON_FILE_INVALID');
  }
  const bytes = await readFile(path);
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  if (text.startsWith('\uFEFF')) throw new Error('JSON_BOM_FORBIDDEN');
  rejectDuplicateKeys(text);
  return JSON.parse(text);
}

async function regularFiles(root) {
  const output = [];
  async function walk(current) {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const path = resolve(current, entry.name);
      const info = await lstat(path);
      if (info.isSymbolicLink()) throw new Error('PACKAGE_SYMLINK_FORBIDDEN');
      if (info.isDirectory()) {
        await walk(path);
      } else if (info.isFile()) {
        output.push(relative(root, path).split(sep).join('/'));
      } else {
        throw new Error('PACKAGE_SPECIAL_FILE_FORBIDDEN');
      }
    }
  }
  await walk(root);
  return output.sort();
}

async function requireNonempty(path, failClass) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size === 0) {
    throw new Error(failClass);
  }
}

async function verifyChecksums(root) {
  const checksumName = 'SHA256SUMS.txt';
  const checksumPath = resolve(root, checksumName);
  const text = await readFile(checksumPath, 'utf8');
  const rows = text.split(/\r?\n/).filter(Boolean);
  const expectedFiles = (await regularFiles(root))
    .filter(name => name !== checksumName);
  if (rows.length !== expectedFiles.length) throw new Error('FILE_SET_MISMATCH');
  const seen = new Set();
  for (const row of rows) {
    const match = row.match(/^([0-9a-f]{64})  (.+)$/);
    if (!match) throw new Error('CHECKSUM_ROW_INVALID');
    const [, expected, name] = match;
    if (seen.has(name) || name === checksumName) throw new Error('CHECKSUM_TARGET_INVALID');
    safeChild(root, name);
    seen.add(name);
    const target = resolve(root, name);
    const metadata = await lstat(target);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error('CHECKSUM_TARGET_INVALID');
    }
    if (sha256(await readFile(target)) !== expected) throw new Error('CHECKSUM_MISMATCH');
  }
  if (expectedFiles.some(name => !seen.has(name))) throw new Error('FILE_SET_MISMATCH');
  return rows.length;
}

function isRfc3339Utc(value) {
  if (typeof value !== 'string'
      || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value)) return false;
  const date = new Date(value);
  return Number.isFinite(date.valueOf()) && date.toISOString() === value;
}

function oidMatches(value, algorithm, hex) {
  const length = algorithm === 'sha256' ? 64 : algorithm === 'sha1' ? 40 : 0;
  return value?.algorithm === algorithm
    && new RegExp(`^[0-9a-f]{${length}}$`).test(value?.hex ?? '')
    && value.hex === hex;
}

async function verifyEvidenceIndex(root, options, objectFormat) {
  const index = await strictJson(resolve(root, 'evidence-index.json'));
  if (index?.schema_version !== 1
      || index.subject?.repository !== options.repository
      || index.subject?.pull_request !== Number(options['pull-request'])
      || !oidMatches(index.subject?.head_oid, objectFormat, options.head)
      || !oidMatches(index.subject?.tree_oid, objectFormat, options.tree)
      || index.workflow?.runner_kind !== 'github-hosted'
      || !/^[1-9]\d*$/.test(index.workflow?.run_id ?? '')
      || !Number.isSafeInteger(index.workflow?.run_attempt)
      || index.workflow.run_attempt < 1
      || index.workflow?.workflow_ref !== options.workflow
      || !Array.isArray(index.runs)
      || index.runs.length === 0) {
    throw new Error('EVIDENCE_INDEX_INVALID');
  }
  const actualContextPaths = new Set(
    (await regularFiles(resolve(root, 'contexts')))
      .filter(path => path.endsWith('.json'))
      .map(path => `contexts/${path}`),
  );
  const seenContexts = new Set();
  for (const run of index.runs) {
    if (typeof run.runner !== 'string'
        || !/^[a-z0-9][a-z0-9._-]{0,63}$/.test(run.runner)
        || typeof run.command !== 'string'
        || run.command.length < 1
        || run.command.length > 4096
        || run.exit_code !== 0
        || !isRfc3339Utc(run.started_at)
        || !isRfc3339Utc(run.finished_at)
        || Date.parse(run.finished_at) < Date.parse(run.started_at)
        || typeof run.os !== 'string'
        || typeof run.arch !== 'string'
        || !oidMatches(run.execution_oid, objectFormat, options.head)
        || !oidMatches(run.tree_oid, objectFormat, options.tree)
        || !/^reports\/[A-Za-z0-9._/-]+$/.test(run.raw_result_path ?? '')
        || !/^contexts\/[A-Za-z0-9._/-]+$/.test(run.context_path ?? '')
        || !/^[0-9a-f]{64}$/.test(run.raw_result_sha256 ?? '')
        || !/^[0-9a-f]{64}$/.test(run.context_sha256 ?? '')
        || typeof run.tool_versions !== 'object'
        || run.tool_versions === null
        || Object.keys(run.tool_versions).length === 0) {
      throw new Error('EVIDENCE_RUN_INVALID');
    }
    if (seenContexts.has(run.context_path)) throw new Error('EVIDENCE_RUN_DUPLICATE');
    seenContexts.add(run.context_path);
    const report = safeChild(root, run.raw_result_path);
    const contextPath = safeChild(root, run.context_path);
    if (sha256(await readFile(report)) !== run.raw_result_sha256
        || sha256(await readFile(contextPath)) !== run.context_sha256) {
      throw new Error('EVIDENCE_RUN_DIGEST_MISMATCH');
    }
    const context = await strictJson(contextPath);
    if (context.subject_pr_head !== options.head
        || context.execution_commit !== options.head
        || context.tree_oid?.algorithm !== objectFormat
        || context.tree_oid?.hex !== options.tree
        || context.runner_kind !== 'github-hosted'
        || context.workflow_run_id !== index.workflow.run_id
        || context.workflow_run_attempt !== index.workflow.run_attempt
        || context.workflow_ref !== options.workflow
        || context.exit_code !== 0
        || context.report_sha256 !== run.raw_result_sha256) {
      throw new Error('CONTEXT_IDENTITY_INVALID');
    }
  }
  if (actualContextPaths.size !== seenContexts.size
      || [...actualContextPaths].some(path => !seenContexts.has(path))) {
    throw new Error('CONTEXT_SET_MISMATCH');
  }
  return index.runs.length;
}

function containsDigest(value, expected) {
  if (value === expected) return true;
  if (Array.isArray(value)) return value.some(item => containsDigest(item, expected));
  if (value && typeof value === 'object') {
    return Object.values(value).some(item => containsDigest(item, expected));
  }
  return false;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  for (const key of [
    'package', 'zip', 'detached', 'attestation-bundle', 'repository',
    'pull-request', 'head', 'tree', 'workflow', 'source-digest',
  ]) {
    if (!options[key]) throw new Error(`REQUIRED_${key.toUpperCase()}_MISSING`);
  }
  const root = resolve(options.package);
  const actualHead = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const actualTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim();
  const objectFormat = execFileSync('git', ['rev-parse', '--show-object-format'], {
    encoding: 'utf8',
  }).trim();
  const oidLength = objectFormat === 'sha256' ? 64 : objectFormat === 'sha1' ? 40 : 0;
  if (!new RegExp(`^[0-9a-f]{${oidLength}}$`).test(options['source-digest'])) {
    throw new Error('ATTESTATION_SOURCE_DIGEST_INVALID');
  }
  if (actualHead !== options.head || actualTree !== options.tree) {
    throw new Error('CHECKOUT_IDENTITY_MISMATCH');
  }

  const checksumCount = await verifyChecksums(root);
  for (const [path, failClass] of [
    ['source/source.zip', 'FULL_SOURCE_ARCHIVE_MISSING'],
    ['source/git-ls-tree.txt', 'TREE_MANIFEST_MISSING'],
    ['source/correction.patch', 'CORRECTION_PATCH_MISSING'],
    ['reports/required-node-audit.json', 'REQUIRED_NODE_REPORT_MISSING'],
    ['manifests/required-tests.v2.json', 'REQUIRED_TEST_MANIFEST_MISSING'],
    ['manifests/action-pins.v1.json', 'ACTION_PIN_MANIFEST_MISSING'],
  ]) {
    await requireNonempty(resolve(root, path), failClass);
  }
  const runCount = await verifyEvidenceIndex(root, options, objectFormat);

  const zip = resolve(options.zip);
  const detached = (await readFile(resolve(options.detached), 'utf8')).trim().split(/\s+/)[0];
  if (!/^[0-9a-f]{64}$/.test(detached)) throw new Error('DETACHED_DIGEST_INVALID');
  const zipDigest = sha256(await readFile(zip));
  if (zipDigest !== detached) throw new Error('DETACHED_DIGEST_MISMATCH');

  await requireNonempty(resolve(options['attestation-bundle']), 'ATTESTATION_BUNDLE_MISSING');
  const verified = spawnSync(
    'gh',
    [
      'attestation', 'verify', zip,
      '--repo', options.repository,
      '--bundle', resolve(options['attestation-bundle']),
      '--format', 'json',
      '--signer-workflow', `${options.repository}/.github/workflows/firstscreen-v2-5.yml`,
      '--source-digest', options['source-digest'],
      '--deny-self-hosted-runners',
    ],
    { encoding: 'utf8' },
  );
  if (verified.status !== 0) throw new Error('ATTESTATION_VERIFY_FAILED');
  const attestation = JSON.parse(verified.stdout);
  if (!containsDigest(attestation, zipDigest)) throw new Error('ATTESTATION_SUBJECT_MISMATCH');

  const result = {
    schema_version: 1,
    subject_head: options.head,
    subject_tree: options.tree,
    object_format: objectFormat,
    checksum_count: checksumCount,
    evidence_run_count: runCount,
    zip_sha256: zipDigest,
    detached_digest_match: true,
    attestation_verified: true,
    attestation_repository: options.repository,
    attestation_workflow: options.workflow,
    attestation_source_commit: options['source-digest'],
  };
  if (options.output) {
    await writeFile(resolve(options.output), `${JSON.stringify(result, null, 2)}\n`);
  }
  console.log('FIRSTSCREEN_EVIDENCE_VERIFY=PASS');
}

main().catch(error => {
  console.error(`FIRSTSCREEN_EVIDENCE_VERIFY=FAIL:${error.message}`);
  process.exitCode = 1;
});
