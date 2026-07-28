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
import { isAbsolute, relative, resolve, sep } from 'node:path';

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
  if (!value || isAbsolute(value) || value.includes('\0')) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  const target = resolve(root, value);
  const rel = relative(root, target);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) {
    throw new Error('PACKAGE_PATH_INVALID');
  }
  return target;
}

async function assertNoSymlinks(root, current = root) {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const target = resolve(current, entry.name);
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink()) throw new Error('PACKAGE_SYMLINK_FORBIDDEN');
    if (metadata.isDirectory()) await assertNoSymlinks(root, target);
  }
}

async function requireNonempty(path, failClass) {
  const metadata = await stat(path);
  if (!metadata.isFile() || metadata.size === 0) throw new Error(failClass);
}

async function verifyChecksums(root) {
  const checksumPath = resolve(root, 'SHA256SUMS');
  const text = await readFile(checksumPath, 'utf8');
  const rows = text.split(/\r?\n/).filter(Boolean);
  if (rows.length === 0) throw new Error('CHECKSUMS_EMPTY');
  const seen = new Set();
  for (const row of rows) {
    const match = row.match(/^([0-9a-f]{64})  (.+)$/);
    if (!match) throw new Error('CHECKSUM_ROW_INVALID');
    const [, expected, name] = match;
    if (seen.has(name) || name === 'SHA256SUMS') {
      throw new Error('CHECKSUM_TARGET_INVALID');
    }
    seen.add(name);
    const target = safeChild(root, name);
    const metadata = await lstat(target);
    if (!metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error('CHECKSUM_TARGET_INVALID');
    }
    const actual = sha256(await readFile(target));
    if (actual !== expected) throw new Error('CHECKSUM_MISMATCH');
  }
  return rows.length;
}

async function verifyContexts(root) {
  const contextsRoot = resolve(root, 'contexts');
  const entries = await readdir(contextsRoot);
  const contexts = entries.filter(name => name.endsWith('.json'));
  if (contexts.length === 0) throw new Error('CONTEXT_MISSING');
  for (const name of contexts) {
    const value = JSON.parse(await readFile(resolve(contextsRoot, name), 'utf8'));
    if (value?.schema_version !== 1
        || !/^[0-9a-f]{40}$/.test(value.subject_pr_head ?? '')
        || !/^[0-9a-f]{40}$/.test(value.execution_commit ?? '')
        || value.tree_oid?.algorithm !== 'sha1'
        || !/^[0-9a-f]{40}$/.test(value.tree_oid?.hex ?? '')
        || !/^\d+$/.test(value.workflow_run_id ?? '')
        || !/^[0-9a-f]{64}$/.test(value.report_sha256 ?? '')) {
      throw new Error('CONTEXT_INVALID');
    }
  }
  return contexts.length;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!options.package || !options.zip || !options.detached
      || !options['attestation-bundle'] || !options.repository) {
    throw new Error('REQUIRED_INPUT_MISSING');
  }
  const root = resolve(options.package);
  await assertNoSymlinks(root);
  const checksumCount = await verifyChecksums(root);
  for (const [path, failClass] of [
    ['source/source.zip', 'FULL_SOURCE_ARCHIVE_MISSING'],
    ['source/git-ls-tree.txt', 'TREE_MANIFEST_MISSING'],
    ['source/correction.patch', 'CORRECTION_PATCH_MISSING'],
    ['reports/required-node-audit.json', 'REQUIRED_NODE_REPORT_MISSING'],
  ]) {
    await requireNonempty(resolve(root, path), failClass);
  }
  const contextCount = await verifyContexts(root);

  const zip = resolve(options.zip);
  const detached = (await readFile(resolve(options.detached), 'utf8'))
    .trim()
    .split(/\s+/)[0];
  if (!/^[0-9a-f]{64}$/.test(detached)) {
    throw new Error('DETACHED_DIGEST_INVALID');
  }
  const zipDigest = sha256(await readFile(zip));
  if (zipDigest !== detached) throw new Error('DETACHED_DIGEST_MISMATCH');

  await requireNonempty(
    resolve(options['attestation-bundle']),
    'ATTESTATION_BUNDLE_MISSING',
  );
  const verified = spawnSync(
    'gh',
    [
      'attestation',
      'verify',
      zip,
      '--repo',
      options.repository,
      '--bundle',
      resolve(options['attestation-bundle']),
    ],
    { encoding: 'utf8' },
  );
  if (verified.status !== 0) throw new Error('ATTESTATION_VERIFY_FAILED');

  const result = {
    schema_version: 1,
    checksum_count: checksumCount,
    context_count: contextCount,
    zip_sha256: zipDigest,
    detached_digest_match: true,
    attestation_verified: true,
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

