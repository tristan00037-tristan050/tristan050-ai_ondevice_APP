import canonicalJsonString from '../../../../packages/common/src/crypto/jcs';

export interface Helper1ExecutionTrustAnchor {
  schema_version: 'butler.helper1.execution-trust-anchor.v1';
  public_key_b64: string;
  public_key_sha256: string;
  session_digest: string;
  subject_commit: string;
  subject_tree: string;
}

export interface Helper1ExecutionReceipt {
  schema_version: 'butler.helper1.execution-receipt.v3';
  key_id: string;
  subject_commit: string;
  subject_tree: string;
  workspace_id: string;
  generation_id: string;
  request_id: string;
  session_digest: string;
  action: 'ask' | 'search' | 'display';
  nonce_digest: string;
  answer_sha256: string | null;
  issued_at_epoch_s: number;
  expires_at_epoch_s: number;
  signature_b64: string;
}

export interface ExpectedExecutionScope {
  requestId: string;
  workspaceId: string;
  generationId: string;
  action: 'ask' | 'search' | 'display';
  answer: string | null;
}

export class Helper1ReceiptError extends Error {
  constructor(readonly reasonCode: string) {
    super(reasonCode);
    this.name = 'Helper1ReceiptError';
  }
}

const SHA256_RE = /^[0-9a-f]{64}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const GIT_OBJECT_RE = /^[0-9a-f]{40}(?:[0-9a-f]{24})?$/;
const B64_RE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const RECEIPT_KEYS = [
  'action',
  'answer_sha256',
  'expires_at_epoch_s',
  'generation_id',
  'issued_at_epoch_s',
  'key_id',
  'nonce_digest',
  'request_id',
  'schema_version',
  'session_digest',
  'signature_b64',
  'subject_commit',
  'subject_tree',
  'workspace_id',
] as const;
const ANCHOR_KEYS = [
  'public_key_b64',
  'public_key_sha256',
  'schema_version',
  'session_digest',
  'subject_commit',
  'subject_tree',
] as const;
const seenReceipts = new Set<string>();

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function decodeBase64(value: string, expectedLength: number): Uint8Array {
  if (!B64_RE.test(value)) throw new Helper1ReceiptError('HELPER1_SIGNATURE_ENCODING_INVALID');
  let decoded: string;
  try {
    decoded = atob(value);
  } catch {
    throw new Helper1ReceiptError('HELPER1_SIGNATURE_ENCODING_INVALID');
  }
  if (decoded.length !== expectedLength) {
    throw new Helper1ReceiptError('HELPER1_SIGNATURE_SIZE_INVALID');
  }
  return Uint8Array.from(decoded, character => character.charCodeAt(0));
}

function canonicalJson(value: unknown): Uint8Array {
  return new TextEncoder().encode(canonicalJsonString(value));
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

function parseAnchor(value: unknown): Helper1ExecutionTrustAnchor {
  if (
    !isObject(value)
    || !hasExactKeys(value, ANCHOR_KEYS)
    || value.schema_version !== 'butler.helper1.execution-trust-anchor.v1'
    || typeof value.public_key_b64 !== 'string'
    || typeof value.public_key_sha256 !== 'string'
    || !SHA256_RE.test(value.public_key_sha256)
    || typeof value.session_digest !== 'string'
    || !SHA256_RE.test(value.session_digest)
    || typeof value.subject_commit !== 'string'
    || !GIT_OBJECT_RE.test(value.subject_commit)
    || typeof value.subject_tree !== 'string'
    || !GIT_OBJECT_RE.test(value.subject_tree)
  ) {
    throw new Helper1ReceiptError('HELPER1_TRUST_ANCHOR_INVALID');
  }
  return value as unknown as Helper1ExecutionTrustAnchor;
}

function parseReceipt(value: unknown): Helper1ExecutionReceipt {
  if (
    !isObject(value)
    || !hasExactKeys(value, RECEIPT_KEYS)
    || value.schema_version !== 'butler.helper1.execution-receipt.v3'
    || typeof value.key_id !== 'string'
    || !SHA256_RE.test(value.key_id)
    || typeof value.subject_commit !== 'string'
    || !GIT_OBJECT_RE.test(value.subject_commit)
    || typeof value.subject_tree !== 'string'
    || !GIT_OBJECT_RE.test(value.subject_tree)
    || typeof value.workspace_id !== 'string'
    || !UUID_RE.test(value.workspace_id)
    || typeof value.generation_id !== 'string'
    || !UUID_RE.test(value.generation_id)
    || typeof value.request_id !== 'string'
    || !UUID_RE.test(value.request_id)
    || typeof value.session_digest !== 'string'
    || !SHA256_RE.test(value.session_digest)
    || !['ask', 'search', 'display'].includes(String(value.action))
    || typeof value.nonce_digest !== 'string'
    || !SHA256_RE.test(value.nonce_digest)
    || !(value.answer_sha256 === null || (typeof value.answer_sha256 === 'string' && SHA256_RE.test(value.answer_sha256)))
    || !Number.isSafeInteger(value.issued_at_epoch_s)
    || !Number.isSafeInteger(value.expires_at_epoch_s)
    || typeof value.signature_b64 !== 'string'
  ) {
    throw new Helper1ReceiptError('HELPER1_EXECUTION_RECEIPT_INVALID');
  }
  return value as unknown as Helper1ExecutionReceipt;
}

export async function verifyHelper1ExecutionReceipt(
  receiptValue: unknown,
  anchorValue: unknown,
  expected: ExpectedExecutionScope,
  nowEpochS = Math.floor(Date.now() / 1000),
): Promise<Helper1ExecutionReceipt> {
  const anchor = parseAnchor(anchorValue);
  const receipt = parseReceipt(receiptValue);
  const publicKey = decodeBase64(anchor.public_key_b64, 32);
  if (await sha256Hex(publicKey) !== anchor.public_key_sha256) {
    throw new Helper1ReceiptError('HELPER1_TRUST_ANCHOR_DIGEST_MISMATCH');
  }
  const answerDigest = expected.answer === null
    ? null
    : await sha256Hex(new TextEncoder().encode(expected.answer));
  if (
    receipt.key_id !== anchor.public_key_sha256
    || receipt.subject_commit !== anchor.subject_commit
    || receipt.subject_tree !== anchor.subject_tree
    || receipt.session_digest !== anchor.session_digest
    || receipt.request_id !== expected.requestId
    || receipt.workspace_id !== expected.workspaceId
    || receipt.generation_id !== expected.generationId
    || receipt.action !== expected.action
    || receipt.answer_sha256 !== answerDigest
  ) {
    throw new Helper1ReceiptError('HELPER1_EXECUTION_SCOPE_MISMATCH');
  }
  if (
    receipt.issued_at_epoch_s > nowEpochS + 5
    || nowEpochS >= receipt.expires_at_epoch_s
    || receipt.expires_at_epoch_s <= receipt.issued_at_epoch_s
    || receipt.expires_at_epoch_s - receipt.issued_at_epoch_s > 60
  ) {
    throw new Helper1ReceiptError('HELPER1_EXECUTION_RECEIPT_NOT_CURRENT');
  }
  const signature = decodeBase64(receipt.signature_b64, 64);
  const { signature_b64: _signature, ...unsigned } = receipt;
  const key = await crypto.subtle.importKey('raw', asArrayBuffer(publicKey), { name: 'Ed25519' }, false, ['verify']);
  const verified = await crypto.subtle.verify(
    { name: 'Ed25519' },
    key,
    asArrayBuffer(signature),
    asArrayBuffer(canonicalJson(unsigned)),
  );
  if (!verified) throw new Helper1ReceiptError('HELPER1_EXECUTION_SIGNATURE_INVALID');
  const replayKey = `${receipt.key_id}:${receipt.session_digest}:${receipt.nonce_digest}`;
  if (seenReceipts.has(replayKey)) {
    throw new Helper1ReceiptError('HELPER1_EXECUTION_RECEIPT_REPLAYED');
  }
  seenReceipts.add(replayKey);
  return receipt;
}

export function clearHelper1ReceiptReplayStateForTests(): void {
  seenReceipts.clear();
}
