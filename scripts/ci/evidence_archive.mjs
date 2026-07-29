import { createHash } from 'node:crypto';
import {
  lstat,
  readFile,
  readdir,
} from 'node:fs/promises';
import {
  isAbsolute,
  relative,
  resolve,
  sep,
} from 'node:path';

const MAX_ENTRIES = 4_096;
const MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024;
const MAX_SINGLE_UNCOMPRESSED = 64 * 1024 * 1024;
const MAX_RATIO = 100;
const EOCD = 0x06054b50;
const CENTRAL = 0x02014b50;
const LOCAL = 0x04034b50;
const WINDOWS_DEVICE = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/iu;

export class EvidenceArchiveError extends Error {}

function fail(code) {
  throw new EvidenceArchiveError(code);
}
function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function decodeName(raw) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(raw);
  } catch {
    fail('ARCHIVE_NAME_UTF8_INVALID');
  }
}

function safeName(name, collisions) {
  if (typeof name !== 'string' || !name || name.includes('\0')
      || name.includes('\\') || isAbsolute(name) || name.endsWith('/')) {
    fail('ARCHIVE_PATH_INVALID');
  }
  const parts = name.split('/');
  if (parts.some(part => !part || part === '.' || part === '..')) {
    fail('ARCHIVE_PATH_INVALID');
  }
  for (const part of parts) {
    if (part.endsWith('.') || part.endsWith(' ') || part.includes(':')
        || WINDOWS_DEVICE.test(part)) {
      fail('ARCHIVE_WINDOWS_PATH_INVALID');
    }
  }
  const normalized = name.normalize('NFC').toLocaleLowerCase('en-US');
  if (collisions.has(normalized)) fail('ARCHIVE_PATH_COLLISION');
  collisions.add(normalized);
  return name.normalize('NFC');
}

function findEocd(buffer) {
  const floor = Math.max(0, buffer.length - 65_557);
  for (let offset = buffer.length - 22; offset >= floor; offset -= 1) {
    if (buffer.readUInt32LE(offset) === EOCD) return offset;
  }
  fail('ARCHIVE_EOCD_MISSING');
}

export function preflightZipBuffer(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 22) fail('ARCHIVE_INVALID');
  const eocd = findEocd(buffer);
  const disk = buffer.readUInt16LE(eocd + 4);
  const centralDisk = buffer.readUInt16LE(eocd + 6);
  const diskEntries = buffer.readUInt16LE(eocd + 8);
  const entries = buffer.readUInt16LE(eocd + 10);
  const centralBytes = buffer.readUInt32LE(eocd + 12);
  const centralOffset = buffer.readUInt32LE(eocd + 16);
  const commentBytes = buffer.readUInt16LE(eocd + 20);
  if (disk !== 0 || centralDisk !== 0 || diskEntries !== entries
      || entries === 0 || entries > MAX_ENTRIES
      || entries === 0xffff || centralBytes === 0xffffffff
      || centralOffset === 0xffffffff
      || eocd + 22 + commentBytes !== buffer.length
      || centralOffset + centralBytes !== eocd) {
    fail('ARCHIVE_DIRECTORY_INVALID');
  }

  const collisions = new Set();
  const result = [];
  let total = 0;
  let cursor = centralOffset;
  for (let index = 0; index < entries; index += 1) {
    if (cursor + 46 > eocd || buffer.readUInt32LE(cursor) !== CENTRAL) {
      fail('ARCHIVE_DIRECTORY_INVALID');
    }
    const madeBy = buffer.readUInt16LE(cursor + 4);
    const flags = buffer.readUInt16LE(cursor + 8);
    const method = buffer.readUInt16LE(cursor + 10);
    const compressed = buffer.readUInt32LE(cursor + 20);
    const uncompressed = buffer.readUInt32LE(cursor + 24);
    const nameBytes = buffer.readUInt16LE(cursor + 28);
    const extraBytes = buffer.readUInt16LE(cursor + 30);
    const entryCommentBytes = buffer.readUInt16LE(cursor + 32);
    const externalAttributes = buffer.readUInt32LE(cursor + 38);
    const localOffset = buffer.readUInt32LE(cursor + 42);
    const end = cursor + 46 + nameBytes + extraBytes + entryCommentBytes;
    if (end > eocd || nameBytes === 0 || localOffset + 30 > centralOffset) {
      fail('ARCHIVE_DIRECTORY_INVALID');
    }
    if ((flags & 0x1) !== 0) fail('ARCHIVE_ENCRYPTED');
    if (![0, 8].includes(method)) fail('ARCHIVE_COMPRESSION_UNSUPPORTED');
    const name = safeName(
      decodeName(buffer.subarray(cursor + 46, cursor + 46 + nameBytes)),
      collisions,
    );
    const host = madeBy >>> 8;
    const unixMode = externalAttributes >>> 16;
    const fileType = unixMode & 0xf000;
    if (host === 3 && fileType !== 0 && fileType !== 0x8000) {
      fail('ARCHIVE_FILE_TYPE_INVALID');
    }
    if (uncompressed > MAX_SINGLE_UNCOMPRESSED) {
      fail('ARCHIVE_ENTRY_SIZE_INVALID');
    }
    total += uncompressed;
    if (total > MAX_TOTAL_UNCOMPRESSED) fail('ARCHIVE_TOTAL_SIZE_INVALID');
    if (uncompressed > 0 && (
      compressed === 0 || uncompressed / compressed > MAX_RATIO
    )) {
      fail('ARCHIVE_COMPRESSION_RATIO_INVALID');
    }

    if (buffer.readUInt32LE(localOffset) !== LOCAL) {
      fail('ARCHIVE_LOCAL_HEADER_INVALID');
    }
    const localFlags = buffer.readUInt16LE(localOffset + 6);
    const localMethod = buffer.readUInt16LE(localOffset + 8);
    const localNameBytes = buffer.readUInt16LE(localOffset + 26);
    const localExtraBytes = buffer.readUInt16LE(localOffset + 28);
    const localNameStart = localOffset + 30;
    const dataStart = localNameStart + localNameBytes + localExtraBytes;
    if (dataStart + compressed > centralOffset
        || localFlags !== flags || localMethod !== method
        || localNameBytes !== nameBytes
        || !buffer.subarray(localNameStart, localNameStart + localNameBytes)
          .equals(buffer.subarray(cursor + 46, cursor + 46 + nameBytes))) {
      fail('ARCHIVE_LOCAL_HEADER_INVALID');
    }
    result.push(Object.freeze({
      name,
      compressedBytes: compressed,
      uncompressedBytes: uncompressed,
    }));
    cursor = end;
  }
  if (cursor !== eocd) fail('ARCHIVE_DIRECTORY_INVALID');
  return Object.freeze(result);
}

export async function preflightZipFile(path) {
  const metadata = await lstat(resolve(path));
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    fail('ARCHIVE_FILE_INVALID');
  }
  return preflightZipBuffer(await readFile(resolve(path)));
}

export async function verifyDetachedSha(zipPath, detachedPath) {
  const zip = resolve(zipPath);
  const detached = resolve(detachedPath);
  const [zipMetadata, detachedMetadata] = await Promise.all([
    lstat(zip),
    lstat(detached),
  ]);
  if (!zipMetadata.isFile() || zipMetadata.isSymbolicLink()
      || !detachedMetadata.isFile() || detachedMetadata.isSymbolicLink()) {
    fail('DETACHED_FILE_INVALID');
  }
  const text = (await readFile(detached, 'utf8')).trim();
  const match = text.match(/^([0-9a-f]{64})(?:  |\s+)([^/\s][^\r\n]*)$/u);
  if (!match || sha256(await readFile(zip)) !== match[1]) {
    fail('DETACHED_DIGEST_MISMATCH');
  }
  return match[1];
}

function safeRelative(name) {
  if (!name || name.includes('\\') || name.includes('\0') || isAbsolute(name)
      || name.split('/').some(part => !part || part === '.' || part === '..')) {
    fail('CHECKSUM_PATH_INVALID');
  }
  return name;
}

async function collectFiles(root, current = root, result = []) {
  for (const entry of await readdir(current, { withFileTypes: true })) {
    const target = resolve(current, entry.name);
    const metadata = await lstat(target);
    if (metadata.isSymbolicLink()) fail('CHECKSUM_FILE_TYPE_INVALID');
    if (metadata.isDirectory()) await collectFiles(root, target, result);
    else if (metadata.isFile()) {
      result.push(relative(root, target).replaceAll(sep, '/'));
    } else fail('CHECKSUM_FILE_TYPE_INVALID');
  }
  return result;
}

export async function verifyChecksumManifest(rootPath) {
  const root = resolve(rootPath);
  const names = await collectFiles(root);
  const manifestName = 'SHA256SUMS.txt';
  if (!names.includes(manifestName)) fail('CHECKSUM_MANIFEST_MISSING');
  const rows = (await readFile(resolve(root, manifestName), 'utf8'))
    .split(/\r?\n/u).filter(Boolean);
  const seen = new Set();
  for (const row of rows) {
    const match = row.match(/^([0-9a-f]{64})  (.+)$/u);
    if (!match) fail('CHECKSUM_ROW_INVALID');
    const name = safeRelative(match[2]);
    if (name === manifestName || seen.has(name)) fail('CHECKSUM_TARGET_INVALID');
    seen.add(name);
    const target = resolve(root, name);
    const rel = relative(root, target);
    if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) {
      fail('CHECKSUM_PATH_INVALID');
    }
    const metadata = await lstat(target);
    if (!metadata.isFile() || metadata.isSymbolicLink()
        || sha256(await readFile(target)) !== match[1]) {
      fail('CHECKSUM_MISMATCH');
    }
  }
  const expected = names.filter(name => name !== manifestName).sort();
  if (JSON.stringify([...seen].sort()) !== JSON.stringify(expected)) {
    fail('CHECKSUM_FILESET_MISMATCH');
  }
  return rows.length;
}
