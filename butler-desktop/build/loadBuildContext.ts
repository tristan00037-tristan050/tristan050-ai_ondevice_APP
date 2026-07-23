import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

export interface ProductionBuildContext {
  schema_version: 'butler.firstscreen.build-context.v1';
  mode: 'production';
  repository: string;
  commit_oid: string;
  tree_oid: string;
  source_manifest_digest: string;
  python_lock_digest: string;
  npm_lock_digest: string;
  cargo_lock_digest: string;
  toolchain_identity: string;
  workflow_identity: string;
  created_at_utc: string;
}

const EXPECTED_KEYS = [
  'schema_version',
  'mode',
  'repository',
  'commit_oid',
  'tree_oid',
  'source_manifest_digest',
  'python_lock_digest',
  'npm_lock_digest',
  'cargo_lock_digest',
  'toolchain_identity',
  'workflow_identity',
  'created_at_utc',
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function assertStrictJson(text: string): void {
  let offset = 0;
  const fail = () => { throw new Error('BUILD_CONTEXT_JSON_INVALID'); };
  const whitespace = () => {
    while (offset < text.length && /[\u0009\u000a\u000d\u0020]/.test(text[offset])) offset += 1;
  };
  const string = (): string => {
    if (text[offset] !== '"') fail();
    const start = offset;
    offset += 1;
    while (offset < text.length) {
      const character = text[offset++];
      if (character === '"') {
        try {
          return JSON.parse(text.slice(start, offset)) as string;
        } catch {
          fail();
        }
      }
      if (character === '\\') {
        if (offset >= text.length) fail();
        const escaped = text[offset++];
        if (escaped === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(offset, offset + 4))) fail();
          offset += 4;
        } else if (!'"\\/bfnrt'.includes(escaped)) {
          fail();
        }
      } else if (character.charCodeAt(0) < 0x20) {
        fail();
      }
    }
    fail();
  };
  const value = (depth: number): void => {
    if (depth > 32) fail();
    whitespace();
    if (text[offset] === '{') {
      offset += 1;
      whitespace();
      const keys = new Set<string>();
      if (text[offset] === '}') { offset += 1; return; }
      while (offset < text.length) {
        const key = string();
        if (keys.has(key)) throw new Error('BUILD_CONTEXT_DUPLICATE_KEY');
        keys.add(key);
        whitespace();
        if (text[offset++] !== ':') fail();
        value(depth + 1);
        whitespace();
        const separator = text[offset++];
        if (separator === '}') return;
        if (separator !== ',') fail();
        whitespace();
      }
      fail();
    }
    if (text[offset] === '[') {
      offset += 1;
      whitespace();
      if (text[offset] === ']') { offset += 1; return; }
      while (offset < text.length) {
        value(depth + 1);
        whitespace();
        const separator = text[offset++];
        if (separator === ']') return;
        if (separator !== ',') fail();
      }
      fail();
    }
    if (text[offset] === '"') { string(); return; }
    for (const literal of ['true', 'false', 'null']) {
      if (text.startsWith(literal, offset)) { offset += literal.length; return; }
    }
    const number = text.slice(offset).match(/^-?(?:0|[1-9][0-9]*)/);
    if (number) {
      offset += number[0].length;
      if (/[.eE]/.test(text[offset] ?? '')) throw new Error('BUILD_CONTEXT_NUMBER_INVALID');
      return;
    }
    fail();
  };
  value(0);
  whitespace();
  if (offset !== text.length) fail();
}

function canonical(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new Error('BUILD_CONTEXT_NUMBER_INVALID');
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  throw new Error('BUILD_CONTEXT_TYPE_INVALID');
}

function validate(value: unknown): asserts value is ProductionBuildContext {
  if (!isRecord(value) || Object.keys(value).sort().join('\0') !== [...EXPECTED_KEYS].sort().join('\0')) {
    throw new Error('BUILD_CONTEXT_SCHEMA_INVALID');
  }
  if (value.schema_version !== 'butler.firstscreen.build-context.v1' || value.mode !== 'production') {
    throw new Error('BUILD_CONTEXT_MODE_INVALID');
  }
  if (typeof value.repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value.repository)) {
    throw new Error('BUILD_CONTEXT_REPOSITORY_INVALID');
  }
  if (typeof value.commit_oid !== 'string' || !/^[0-9a-f]{40,64}$/.test(value.commit_oid)) {
    throw new Error('BUILD_CONTEXT_COMMIT_INVALID');
  }
  if (typeof value.tree_oid !== 'string' || !/^[0-9a-f]{40,64}$/.test(value.tree_oid)) {
    throw new Error('BUILD_CONTEXT_TREE_INVALID');
  }
  for (const key of ['source_manifest_digest', 'python_lock_digest', 'npm_lock_digest', 'cargo_lock_digest'] as const) {
    if (typeof value[key] !== 'string' || !/^[0-9a-f]{64}$/.test(value[key])) {
      throw new Error('BUILD_CONTEXT_DIGEST_INVALID');
    }
  }
  if (typeof value.toolchain_identity !== 'string' || value.toolchain_identity.length < 8 || value.toolchain_identity.length > 512) {
    throw new Error('BUILD_CONTEXT_TOOLCHAIN_INVALID');
  }
  if (typeof value.workflow_identity !== 'string' || value.workflow_identity.length < 8 || value.workflow_identity.length > 256) {
    throw new Error('BUILD_CONTEXT_WORKFLOW_INVALID');
  }
  if (typeof value.created_at_utc !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value.created_at_utc)) {
    throw new Error('BUILD_CONTEXT_TIME_INVALID');
  }
  if (Number.isNaN(Date.parse(value.created_at_utc))) throw new Error('BUILD_CONTEXT_TIME_INVALID');
}

export function loadProductionBuildContext(path: string | undefined): {
  context: ProductionBuildContext;
  canonicalBytes: Buffer;
  digest: string;
} {
  if (!path) throw new Error('BUILD_CONTEXT_PATH_REQUIRED');
  const raw = readFileSync(path);
  if (raw.length === 0 || raw.length > 64 * 1024) throw new Error('BUILD_CONTEXT_SIZE_INVALID');
  if (raw.length >= 3 && raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) {
    throw new Error('BUILD_CONTEXT_BOM_INVALID');
  }
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  } catch {
    throw new Error('BUILD_CONTEXT_UTF8_INVALID');
  }
  assertStrictJson(text);
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error('BUILD_CONTEXT_JSON_INVALID');
  }
  validate(value);
  const canonicalBytes = Buffer.from(canonical(value), 'utf8');
  return {
    context: value,
    canonicalBytes,
    digest: createHash('sha256').update(canonicalBytes).digest('hex'),
  };
}
