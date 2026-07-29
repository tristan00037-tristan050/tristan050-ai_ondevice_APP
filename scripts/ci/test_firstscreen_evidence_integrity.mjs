#!/usr/bin/env node
import { createHash } from 'node:crypto';
import {
  mkdir,
  mkdtemp,
  readFile,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';

import {
  EvidenceArchiveError,
  preflightZipBuffer,
  verifyChecksumManifest,
  verifyDetachedSha,
} from './evidence_archive.mjs';

const output = process.argv[2];
await mkdir(tmpdir(), { recursive: true });
const temporary = await mkdtemp(resolve(tmpdir(), 'firstscreen-evidence-'));

function crc32() {
  // Preflight deliberately does not trust or extract payload bytes. CRC
  // validation is performed by the decompressor only after this gate.
  return 0;
}

function zip(entries) {
  const local = [];
  const central = [];
  let localOffset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name, 'utf8');
    const data = Buffer.from(entry.data ?? 'x');
    const flags = entry.flags ?? 0x0800;
    const method = 0;
    const compressed = entry.compressed ?? data.length;
    const uncompressed = entry.uncompressed ?? data.length;
    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(flags, 6);
    localHeader.writeUInt16LE(method, 8);
    localHeader.writeUInt32LE(crc32(data), 14);
    localHeader.writeUInt32LE(compressed, 18);
    localHeader.writeUInt32LE(uncompressed, 22);
    localHeader.writeUInt16LE(name.length, 26);
    const localBody = Buffer.concat([localHeader, name, data]);
    local.push(localBody);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(entry.madeBy ?? 0x0314, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(flags, 8);
    centralHeader.writeUInt16LE(method, 10);
    centralHeader.writeUInt32LE(crc32(data), 16);
    centralHeader.writeUInt32LE(compressed, 20);
    centralHeader.writeUInt32LE(uncompressed, 24);
    centralHeader.writeUInt16LE(name.length, 28);
    centralHeader.writeUInt32LE(entry.externalAttributes ?? 0x81a40000, 38);
    centralHeader.writeUInt32LE(localOffset, 42);
    central.push(Buffer.concat([centralHeader, name]));
    localOffset += localBody.length;
  }
  const centralBody = Buffer.concat(central);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralBody.length, 12);
  eocd.writeUInt32LE(localOffset, 16);
  return Buffer.concat([...local, centralBody, eocd]);
}

function blocked(action, expected) {
  try {
    action();
  } catch (error) {
    if (error instanceof EvidenceArchiveError && error.message === expected) return;
    throw error;
  }
  throw new Error(`ATTACK_ACCEPTED_${expected}`);
}

const nodes = [];
async function test(id, action) {
  await action();
  nodes.push({
    runner: 'node',
    file: 'scripts/ci/test_firstscreen_evidence_integrity.mjs',
    title: id,
    status: 'passed',
  });
}

await test('FSV10-EVIDENCE-001', () => {
  blocked(() => preflightZipBuffer(zip([{ name: '../escape' }])), 'ARCHIVE_PATH_INVALID');
});
await test('FSV10-EVIDENCE-002', () => {
  for (const name of ['/absolute', 'a\\b', 'a//b', 'a/./b']) {
    blocked(() => preflightZipBuffer(zip([{ name }])), 'ARCHIVE_PATH_INVALID');
  }
});
await test('FSV10-EVIDENCE-003', () => {
  blocked(
    () => preflightZipBuffer(zip([{ name: 'A.txt' }, { name: 'a.txt' }])),
    'ARCHIVE_PATH_COLLISION',
  );
  blocked(
    () => preflightZipBuffer(zip([{ name: 'é.txt' }, { name: 'e\u0301.txt' }])),
    'ARCHIVE_PATH_COLLISION',
  );
});
await test('FSV10-EVIDENCE-004', () => {
  for (const name of ['NUL.txt', 'safe:ads', 'trailing.', 'trailing ']) {
    blocked(
      () => preflightZipBuffer(zip([{ name }])),
      'ARCHIVE_WINDOWS_PATH_INVALID',
    );
  }
});
await test('FSV10-EVIDENCE-005', () => {
  blocked(
    () => preflightZipBuffer(zip([{
      name: 'link',
      externalAttributes: 0xa1ff0000,
    }])),
    'ARCHIVE_FILE_TYPE_INVALID',
  );
});
await test('FSV10-EVIDENCE-006', () => {
  blocked(
    () => preflightZipBuffer(zip([{ name: 'secret', flags: 0x0801 }])),
    'ARCHIVE_ENCRYPTED',
  );
});
await test('FSV10-EVIDENCE-009', () => {
  blocked(
    () => preflightZipBuffer(zip([{
      name: 'huge',
      uncompressed: 64 * 1024 * 1024 + 1,
    }])),
    'ARCHIVE_ENTRY_SIZE_INVALID',
  );
});
await test('FSV10-EVIDENCE-010', () => {
  blocked(
    () => preflightZipBuffer(zip([{
      name: 'ratio',
      compressed: 1,
      uncompressed: 101,
    }])),
    'ARCHIVE_COMPRESSION_RATIO_INVALID',
  );
});
await test('FSV11-EVIDENCE-011', async () => {
  const archive = resolve(temporary, 'evidence.zip');
  const detached = resolve(temporary, 'evidence.zip.sha256');
  const content = zip([{ name: 'safe.txt', data: 'safe' }]);
  await writeFile(archive, content);
  const digest = createHash('sha256').update(content).digest('hex');
  await writeFile(detached, `${digest}  evidence.zip\n`);
  if (await verifyDetachedSha(archive, detached) !== digest) {
    throw new Error('DETACHED_VALID_REJECTED');
  }
  await writeFile(detached, `${'0'.repeat(64)}  evidence.zip\n`);
  await (async () => {
    try {
      await verifyDetachedSha(archive, detached);
      throw new Error('DETACHED_ATTACK_ACCEPTED');
    } catch (error) {
      if (error.message !== 'DETACHED_DIGEST_MISMATCH') throw error;
    }
  })();
});
await test('FSV11-EVIDENCE-012', async () => {
  const root = resolve(temporary, 'package');
  await mkdir(resolve(root, 'reports'), { recursive: true });
  const report = Buffer.from('{"ok":true}\n');
  await writeFile(resolve(root, 'reports/result.json'), report);
  const digest = createHash('sha256').update(report).digest('hex');
  await writeFile(
    resolve(root, 'SHA256SUMS.txt'),
    `${digest}  reports/result.json\n`,
  );
  if (await verifyChecksumManifest(root) !== 1) {
    throw new Error('INTERNAL_SHA_VALID_REJECTED');
  }
  await writeFile(resolve(root, 'reports/result.json'), '{"ok":false}\n');
  try {
    await verifyChecksumManifest(root);
    throw new Error('INTERNAL_SHA_ATTACK_ACCEPTED');
  } catch (error) {
    if (error.message !== 'CHECKSUM_MISMATCH') throw error;
  }
});

const result = { schema_version: 1, nodes };
if (output) await writeFile(resolve(output), `${JSON.stringify(result, null, 2)}\n`);
console.log('FIRSTSCREEN_EVIDENCE_INTEGRITY_TESTS_OK=1');
