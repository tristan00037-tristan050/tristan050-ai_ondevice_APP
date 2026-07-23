import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { loadProductionBuildContext } from './loadBuildContext';

function context(): Record<string, string> {
  return {
    schema_version: 'butler.firstscreen.build-context.v1',
    mode: 'production',
    repository: 'atlink/butler',
    commit_oid: '1'.repeat(40),
    tree_oid: '2'.repeat(40),
    source_manifest_digest: '3'.repeat(64),
    python_lock_digest: '4'.repeat(64),
    npm_lock_digest: '5'.repeat(64),
    cargo_lock_digest: '6'.repeat(64),
    toolchain_identity: 'python=3.12;node=24;rust=1.97.1',
    workflow_identity: 'atlink/butler/.github/workflows/firstscreen-v2-5.yml@refs/heads/main',
    created_at_utc: '2026-07-21T00:00:00Z',
  };
}

function temporary(payload: string | Uint8Array): string {
  const path = join(mkdtempSync(join(tmpdir(), 'butler-build-context-')), 'BUILD_CONTEXT.json');
  writeFileSync(path, payload);
  return path;
}

describe('production BUILD_CONTEXT parser', () => {
  it('loads a canonical production identity', () => {
    const loaded = loadProductionBuildContext(temporary(JSON.stringify(context())));
    expect(loaded.context.commit_oid).toBe('1'.repeat(40));
    expect(loaded.digest).toMatch(/^[0-9a-f]{64}$/);
  });

  it('rejects duplicate keys including escaped aliases', () => {
    const valid = JSON.stringify(context());
    const duplicate = valid.replace('"mode":"production"', '"mode":"production","m\\u006fde":"production"');
    expect(() => loadProductionBuildContext(temporary(duplicate))).toThrow('BUILD_CONTEXT_DUPLICATE_KEY');
  });

  it('rejects invalid UTF-8 and a BOM', () => {
    expect(() => loadProductionBuildContext(temporary(new Uint8Array([0xff, 0xfe])))).toThrow('BUILD_CONTEXT_UTF8_INVALID');
    expect(() => loadProductionBuildContext(temporary(`\ufeff${JSON.stringify(context())}`))).toThrow('BUILD_CONTEXT_BOM_INVALID');
  });
});
