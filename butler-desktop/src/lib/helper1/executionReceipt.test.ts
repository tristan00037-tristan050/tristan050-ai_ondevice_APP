import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearHelper1ReceiptReplayStateForTests,
  verifyHelper1ExecutionReceipt,
} from './executionReceipt';

const REQUEST_ID = '9699ce0c-2597-42ea-a6fa-29cfcb2bb75e';
const WORKSPACE_ID = '90321a6a-f937-4d93-b018-d09e8cab4e72';
const GENERATION_ID = '3f201e45-366e-48fc-96d7-21c76c399753';
const SUBJECT_COMMIT = 'a'.repeat(40);
const SUBJECT_TREE = 'b'.repeat(40);
const SESSION_DIGEST = 'c'.repeat(64);
const ANSWER = '회사 규정에 따른 답변입니다.';

function bytesToBase64(value: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(value)));
}

function asArrayBuffer(value: Uint8Array): ArrayBuffer {
  const copy = new ArrayBuffer(value.byteLength);
  new Uint8Array(copy).set(value);
  return copy;
}

async function sha256Hex(value: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', asArrayBuffer(value));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

function canonicalJson(value: Record<string, unknown>): Uint8Array {
  const sorted = Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]));
  return new TextEncoder().encode(JSON.stringify(sorted));
}

async function signedFixture(action: 'ask' | 'search' | 'display' = 'ask') {
  const pair = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  const publicKey = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  const keyDigest = await sha256Hex(publicKey);
  const now = 1_785_500_000;
  const unsigned = {
    schema_version: 'butler.helper1.execution-receipt.v3',
    key_id: keyDigest,
    subject_commit: SUBJECT_COMMIT,
    subject_tree: SUBJECT_TREE,
    workspace_id: WORKSPACE_ID,
    generation_id: GENERATION_ID,
    request_id: REQUEST_ID,
    session_digest: SESSION_DIGEST,
    action,
    nonce_digest: 'd'.repeat(64),
    answer_sha256: await sha256Hex(new TextEncoder().encode(ANSWER)),
    issued_at_epoch_s: now - 1,
    expires_at_epoch_s: now + 30,
  };
  const signature = await crypto.subtle.sign(
    { name: 'Ed25519' },
    pair.privateKey,
    asArrayBuffer(canonicalJson(unsigned)),
  );
  return {
    now,
    anchor: {
      schema_version: 'butler.helper1.execution-trust-anchor.v1',
      public_key_b64: bytesToBase64(publicKey.buffer),
      public_key_sha256: keyDigest,
      session_digest: SESSION_DIGEST,
      subject_commit: SUBJECT_COMMIT,
      subject_tree: SUBJECT_TREE,
    },
    receipt: { ...unsigned, signature_b64: bytesToBase64(signature) },
  };
}

const expected = {
  requestId: REQUEST_ID,
  workspaceId: WORKSPACE_ID,
  generationId: GENERATION_ID,
  action: 'ask' as const,
  answer: ANSWER,
};

describe('Helper1 real Ed25519 execution receipt verification', () => {
  beforeEach(clearHelper1ReceiptReplayStateForTests);

  it('accepts an actual Python Sidecar Ed25519 receipt in Web Crypto', async () => {
    const script = resolve(
      process.cwd(), '..', 'scripts', 'test_support',
      'emit_helper1_execution_receipt.py',
    );
    const python = process.env.HELPER1_TEST_PYTHON ?? 'python3';
    const fixture = JSON.parse(execFileSync(python, [script], { encoding: 'utf-8' }));
    await expect(
      verifyHelper1ExecutionReceipt(
        fixture.receipt, fixture.anchor, fixture.expected, fixture.now,
      ),
    ).resolves.toMatchObject({ request_id: REQUEST_ID, action: 'ask' });
  });

  it('accepts a real Ed25519 signature bound to request, session, action and answer', async () => {
    const fixture = await signedFixture();
    await expect(
      verifyHelper1ExecutionReceipt(fixture.receipt, fixture.anchor, expected, fixture.now),
    ).resolves.toMatchObject({ request_id: REQUEST_ID, action: 'ask' });
  });

  it('rejects action downgrade even when the altered action has a valid signature', async () => {
    const fixture = await signedFixture('display');
    await expect(
      verifyHelper1ExecutionReceipt(fixture.receipt, fixture.anchor, expected, fixture.now),
    ).rejects.toMatchObject({ reasonCode: 'HELPER1_EXECUTION_SCOPE_MISMATCH' });
  });

  it('rejects a valid signed receipt when it is replayed', async () => {
    const fixture = await signedFixture();
    await verifyHelper1ExecutionReceipt(fixture.receipt, fixture.anchor, expected, fixture.now);
    await expect(
      verifyHelper1ExecutionReceipt(fixture.receipt, fixture.anchor, expected, fixture.now),
    ).rejects.toMatchObject({ reasonCode: 'HELPER1_EXECUTION_RECEIPT_REPLAYED' });
  });

  it('rejects signature tampering instead of using a verifier stub', async () => {
    const fixture = await signedFixture();
    const tampered = { ...fixture.receipt, nonce_digest: 'e'.repeat(64) };
    await expect(
      verifyHelper1ExecutionReceipt(tampered, fixture.anchor, expected, fixture.now),
    ).rejects.toMatchObject({ reasonCode: 'HELPER1_EXECUTION_SIGNATURE_INVALID' });
  });
});
