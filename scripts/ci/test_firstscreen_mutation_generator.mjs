#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  EvidenceArchiveError,
  preflightZipBuffer,
} from './evidence_archive.mjs';
import {
  StrictJsonError,
  parseStrictJson,
} from './strict_json.mjs';

const SEEDS = [
  0x4255544c45523131n,
  0x4653563131455649n,
  0x5452555354474154n,
];
const CASES_PER_SEED = 1_000;
const MASK_64 = (1n << 64n) - 1n;

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function xorshift64(seed) {
  let state = seed & MASK_64;
  return () => {
    state ^= state << 13n;
    state ^= state >> 7n;
    state ^= state << 17n;
    state &= MASK_64;
    return state;
  };
}

function zip(entries) {
  const local = [];
  const central = [];
  let localOffset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name, 'utf8');
    const data = Buffer.from(entry.data ?? 'x');
    const flags = entry.flags ?? 0x0800;
    const compressed = entry.compressed ?? data.length;
    const uncompressed = entry.uncompressed ?? data.length;
    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(flags, 6);
    localHeader.writeUInt16LE(0, 8);
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
    centralHeader.writeUInt16LE(0, 10);
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

const operators = [
  {
    name: 'json_duplicate_key',
    run: value => parseStrictJson(`{"k":${value},"k":${value + 1}}`),
    error: [StrictJsonError, 'JSON_DUPLICATE_KEY'],
  },
  {
    name: 'json_nonfinite',
    run: () => parseStrictJson('{"k":NaN}'),
    error: [StrictJsonError, 'JSON_VALUE_INVALID'],
  },
  {
    name: 'json_bom',
    run: () => parseStrictJson(Buffer.concat([
      Buffer.from([0xef, 0xbb, 0xbf]),
      Buffer.from('{"k":1}'),
    ])),
    error: [StrictJsonError, 'JSON_BOM_FORBIDDEN'],
  },
  {
    name: 'json_invalid_utf8',
    run: () => parseStrictJson(Buffer.from([
      0x7b, 0x22, 0xc3, 0x28, 0x22, 0x3a, 0x31, 0x7d,
    ])),
    error: [StrictJsonError, 'JSON_UTF8_INVALID'],
  },
  {
    name: 'json_depth',
    run: () => parseStrictJson(`{"k":${'['.repeat(34)}0${']'.repeat(34)}}`),
    error: [StrictJsonError, 'JSON_TOO_DEEP'],
  },
  {
    name: 'json_size',
    run: () => parseStrictJson(Buffer.alloc(65_537, 0x20)),
    error: [StrictJsonError, 'JSON_TOO_LARGE'],
  },
  {
    name: 'json_unpaired_surrogate',
    run: () => parseStrictJson('{"k":"\\ud800"}'),
    error: [StrictJsonError, 'JSON_UNPAIRED_SURROGATE'],
  },
  {
    name: 'json_unsafe_integer',
    run: () => parseStrictJson('{"k":9007199254740992}'),
    error: [StrictJsonError, 'JSON_INTEGER_UNSAFE'],
  },
  {
    name: 'archive_traversal',
    run: value => preflightZipBuffer(zip([{ name: `../${value}` }])),
    error: [EvidenceArchiveError, 'ARCHIVE_PATH_INVALID'],
  },
  {
    name: 'archive_backslash',
    run: value => preflightZipBuffer(zip([{ name: `a\\${value}` }])),
    error: [EvidenceArchiveError, 'ARCHIVE_PATH_INVALID'],
  },
  {
    name: 'archive_ads',
    run: value => preflightZipBuffer(zip([{ name: `safe${value}:ads` }])),
    error: [EvidenceArchiveError, 'ARCHIVE_WINDOWS_PATH_INVALID'],
  },
  {
    name: 'archive_unicode_case_collision',
    run: value => preflightZipBuffer(zip([
      { name: `Case-${value}.txt` },
      { name: `case-${value}.txt` },
    ])),
    error: [EvidenceArchiveError, 'ARCHIVE_PATH_COLLISION'],
  },
  {
    name: 'archive_encrypted',
    run: value => preflightZipBuffer(zip([{
      name: `encrypted-${value}`,
      flags: 0x0801,
    }])),
    error: [EvidenceArchiveError, 'ARCHIVE_ENCRYPTED'],
  },
  {
    name: 'archive_symlink',
    run: value => preflightZipBuffer(zip([{
      name: `link-${value}`,
      externalAttributes: 0xa1ff0000,
    }])),
    error: [EvidenceArchiveError, 'ARCHIVE_FILE_TYPE_INVALID'],
  },
  {
    name: 'archive_ratio',
    run: value => preflightZipBuffer(zip([{
      name: `ratio-${value}`,
      compressed: 1,
      uncompressed: 101,
    }])),
    error: [EvidenceArchiveError, 'ARCHIVE_COMPRESSION_RATIO_INVALID'],
  },
];

const source = await readFile(fileURLToPath(import.meta.url));
const generatorSha256 = sha256(source);
const reports = [];
let totalAccepted = 0;
let totalUnanalysed = 0;

for (const seed of SEEDS) {
  const random = xorshift64(seed);
  const operatorCounts = Object.fromEntries(
    operators.map(operator => [operator.name, 0]),
  );
  let rejected = 0;
  let acceptedMalicious = 0;
  let unanalysed = 0;
  for (let index = 0; index < CASES_PER_SEED; index += 1) {
    const operator = operators[
      Number((random() + BigInt(index)) % BigInt(operators.length))
    ];
    operatorCounts[operator.name] += 1;
    const value = Number(random() % 1_000_000n);
    try {
      operator.run(value);
      acceptedMalicious += 1;
    } catch (error) {
      const [ErrorClass, code] = operator.error;
      if (error instanceof ErrorClass && error.message === code) rejected += 1;
      else unanalysed += 1;
    }
  }
  totalAccepted += acceptedMalicious;
  totalUnanalysed += unanalysed;
  reports.push({
    generator_version: '1',
    generator_sha256: generatorSha256,
    seed: `0x${seed.toString(16).toUpperCase()}`,
    cases: CASES_PER_SEED,
    operator_counts: operatorCounts,
    rejected,
    accepted_malicious: acceptedMalicious,
    unanalysed,
  });
}

const result = {
  schema_version: 1,
  total_generated_cases: SEEDS.length * CASES_PER_SEED,
  accepted_malicious: totalAccepted,
  unanalysed: totalUnanalysed,
  reports,
};
if (
  result.total_generated_cases < 3_000
  || result.accepted_malicious !== 0
  || result.unanalysed !== 0
) {
  throw new Error(`MUTATION_GATE_FAILED:${JSON.stringify(result)}`);
}
const output = process.argv[2];
if (!output) throw new Error('OUTPUT_REQUIRED');
await writeFile(resolve(output), `${JSON.stringify(result, null, 2)}\n`);
console.log('FIRSTSCREEN_MUTATION_GENERATOR_OK=1');
console.log(`TOTAL_GENERATED_CASES=${result.total_generated_cases}`);
console.log(`ACCEPTED_MALICIOUS=${result.accepted_malicious}`);
console.log(`UNANALYSED=${result.unanalysed}`);
