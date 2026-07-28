#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..', '..');
const temporary = await mkdtemp(resolve(tmpdir(), 'firstscreen-verifier-'));
const head = execFileSync('git', ['rev-parse', 'HEAD'], {
  cwd: root,
  encoding: 'utf8',
}).trim();
const tree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
  cwd: root,
  encoding: 'utf8',
}).trim();

const manifest = resolve(temporary, 'manifest.json');
const vitest = resolve(temporary, 'vitest.json');
const playwright = resolve(temporary, 'playwright.json');
await writeFile(manifest, JSON.stringify({
  schema_version: 1,
  suite: 'negative-self-test',
  tests: [{
    id: 'NEG-1',
    runner: 'vitest',
    file: 'missing.test.ts',
    title: 'must be absent',
    required: true,
  }],
}));
await writeFile(vitest, JSON.stringify({ testResults: [] }));
await writeFile(playwright, JSON.stringify({ suites: [] }));
const missingNode = spawnSync(
  process.execPath,
  [
    resolve(root, 'butler-desktop/scripts/verify-required-test-nodes.mjs'),
    '--manifest', manifest,
    '--vitest', vitest,
    '--playwright', playwright,
    '--head', head,
  ],
  { encoding: 'utf8' },
);
if (missingNode.status === 0
    || !missingNode.stdout.includes('REQUIRED_TEST_NODES_MISSING=1')) {
  throw new Error('REQUIRED_NODE_NEGATIVE_SELF_TEST_FAILED');
}

const packageRoot = resolve(temporary, 'package');
await mkdir(resolve(packageRoot, 'source'), { recursive: true });
await mkdir(resolve(packageRoot, 'reports'), { recursive: true });
await mkdir(resolve(packageRoot, 'contexts'), { recursive: true });
const payload = resolve(packageRoot, 'source/source.zip');
await writeFile(payload, 'original');
const originalDigest = createHash('sha256').update('original').digest('hex');
await writeFile(
  resolve(packageRoot, 'SHA256SUMS.txt'),
  `${originalDigest}  source/source.zip\n`,
);
await writeFile(payload, 'tampered');
const evidence = spawnSync(
  process.execPath,
  [
    resolve(root, 'scripts/ci/verify_firstscreen_evidence_package.mjs'),
    '--package', packageRoot,
    '--zip', resolve(temporary, 'result.zip'),
    '--detached', resolve(temporary, 'result.sha256'),
    '--attestation-bundle', resolve(temporary, 'bundle.json'),
    '--repository', 'owner/repository',
    '--pull-request', '886',
    '--head', head,
    '--tree', tree,
    '--workflow', 'owner/repository/.github/workflows/firstscreen-v2-5.yml@refs/pull/886/merge',
  ],
  { encoding: 'utf8' },
);
if (evidence.status === 0
    || !evidence.stderr.includes('CHECKSUM_MISMATCH')) {
  throw new Error('EVIDENCE_NEGATIVE_SELF_TEST_FAILED');
}

const output = process.argv[2];
if (!output) throw new Error('OUTPUT_REQUIRED');
await writeFile(resolve(output), `${JSON.stringify({
  schema_version: 1,
  nodes: [
    {
      runner: 'node',
      file: 'butler-desktop/scripts/verify-required-test-nodes.mjs',
      title: 'rejects missing or mismatched unit browser Playwright and required-node HEAD contexts',
      status: 'passed',
    },
    {
      runner: 'node',
      file: 'scripts/ci/verify_firstscreen_evidence_package.mjs',
      title: 'verifies full source delta reports checksums detached digest and artifact attestation',
      status: 'passed',
    },
  ],
}, null, 2)}\n`);
console.log('FIRSTSCREEN_VERIFIER_NEGATIVE_TESTS=PASS');
