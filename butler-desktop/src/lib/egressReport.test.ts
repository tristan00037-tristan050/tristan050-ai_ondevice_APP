import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import {
  canonicalEgressReceiptPayload,
  EgressReportError,
  parseEgressReport,
} from './egressReport';

const NOW = Date.parse('2026-07-27T01:00:30Z');
const KEY_ID = 'butler-egress-verifier-test-v1';
const { privateKey, publicKey } = generateKeyPairSync('ed25519');
const PUBLIC_KEY_SPKI_BASE64 = publicKey
  .export({ format: 'der', type: 'spki' })
  .toString('base64');

type WireReport = {
  schema_version: string;
  measurement: 'MEASURED';
  value: number;
  run_id: string;
  measurement_generation: number;
  measurement_started_at: string;
  measured_at: string;
  fresh_until?: string;
  egress_bytes_total: number;
  external_request_count: number;
  raw_file_sent_external: boolean;
  verdict: 'PASS' | 'FAIL';
  receipt_run_id: string;
  receipt_key_id: string;
  receipt_algorithm: 'Ed25519';
  receipt_policy_version: string;
  receipt_digest: `sha256:${string}`;
  receipt_signature: string;
};

function signedReport(overrides: Partial<WireReport> = {}): WireReport {
  const report: WireReport = {
    schema_version: 'butler.egress.report.v3',
    measurement: 'MEASURED',
    value: overrides.egress_bytes_total ?? 0,
    run_id: 'run-001',
    measurement_generation: 7,
    measurement_started_at: '2026-07-27T01:00:00Z',
    measured_at: '2026-07-27T01:00:20Z',
    fresh_until: '2026-07-27T01:01:20Z',
    egress_bytes_total: 0,
    external_request_count: 0,
    raw_file_sent_external: false,
    verdict: 'PASS',
    receipt_run_id: 'run-001',
    receipt_key_id: KEY_ID,
    receipt_algorithm: 'Ed25519',
    receipt_policy_version: 'egress-policy-2026.1',
    receipt_digest: `sha256:${'0'.repeat(64)}`,
    receipt_signature: 'A'.repeat(86),
    ...overrides,
  };
  const digest = createHash('sha256')
    .update(canonicalEgressReceiptPayload(report))
    .digest('hex');
  report.receipt_digest = `sha256:${digest}`;
  report.receipt_signature = sign(
    null,
    Buffer.from(report.receipt_digest, 'utf8'),
    privateKey,
  ).toString('base64url');
  return report;
}

async function errorCode(value: unknown) {
  try {
    await parseEgressReport(value, NOW);
    return 'NO_ERROR';
  } catch (error) {
    return error instanceof EgressReportError ? error.code : 'UNKNOWN';
  }
}

beforeAll(() => {
  vi.stubEnv('VITE_EGRESS_RECEIPT_KEY_ID', KEY_ID);
  vi.stubEnv(
    'VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64',
    PUBLIC_KEY_SPKI_BASE64,
  );
});

afterAll(() => vi.unstubAllEnvs());

describe('parseEgressReport fail-closed contract', () => {
  it('accepts a fresh, body-bound and signature-verified zero report', async () => {
    const report = await parseEgressReport(signedReport(), NOW);
    expect('kind' in report).toBe(false);
    if (!('kind' in report)) {
      expect(report.egressBytesTotal).toBe(0);
      expect(report.measurement).toBe('MEASURED');
      expect(report.value).toBe(0);
      expect(report.measurementGeneration).toBe(7);
      expect(report.receiptKeyId).toBe(KEY_ID);
    }
  });

  it.each([
    [{ ...signedReport(), schema_version: undefined }, 'UNSUPPORTED_SCHEMA'],
    [{ ...signedReport(), schema_version: 'egress_report.v2' }, 'UNSUPPORTED_SCHEMA'],
    [signedReport({ egress_bytes_total: -1 }), 'SCHEMA_INVALID'],
    [signedReport({ egress_bytes_total: Number.MAX_SAFE_INTEGER + 1 }), 'SCHEMA_INVALID'],
    [signedReport({ measurement_generation: 0 }), 'SCHEMA_INVALID'],
    [signedReport({ value: 1 }), 'INCONSISTENT_REPORT'],
    [signedReport({ receipt_run_id: 'other-run' }), 'RECEIPT_UNBOUND'],
    [signedReport({ verdict: 'PASS', egress_bytes_total: 1 }), 'INCONSISTENT_REPORT'],
    [signedReport({ verdict: 'PASS', external_request_count: 1 }), 'INCONSISTENT_REPORT'],
    [signedReport({ verdict: 'PASS', raw_file_sent_external: true }), 'INCONSISTENT_REPORT'],
    [signedReport({ verdict: 'FAIL' }), 'INCONSISTENT_REPORT'],
    [{ ...signedReport(), extra: 'not-allowed' }, 'SCHEMA_INVALID'],
    [signedReport({ measured_at: '2026-07-27T01:02:00Z' }), 'CLOCK_INVALID'],
  ] as const)('rejects invalid or contradictory payload %#', async (payload, code) => {
    expect(await errorCode(payload)).toBe(code);
  });

  it('classifies an exact STATIC_BETA marker as unmeasured without trusting value 0', async () => {
    await expect(parseEgressReport({
      value: 0,
      measurement: 'STATIC_BETA',
      measured_at: null,
    }, NOW)).resolves.toEqual({
      kind: 'unmeasured',
      source: 'STATIC_BETA',
      lastReportedAt: undefined,
    });
    expect(await errorCode({
      value: 0,
      measurement: 'MEASURED',
      measured_at: '2026-07-27T01:00:20Z',
    })).toBe('UNSUPPORTED_SCHEMA');
  });

  it.each([
    '2026-02-30T00:00:00Z',
    '2026-07-27 01:00:20Z',
    '2026-7-27T01:00:20Z',
    '2026-07-27T01:00:60Z',
    '2026-07-27T01:00:20+00:00',
    '0000-01-01T00:00:00Z',
  ])('rejects non-canonical or impossible RFC 3339 value %s', async value => {
    expect(await errorCode(signedReport({ measured_at: value }))).toBe(
      'SCHEMA_INVALID',
    );
  });

  it('validates the whole signed payload before classifying missing freshness', async () => {
    const missing = signedReport();
    delete missing.fresh_until;
    const resigned = signedReport(missing);
    delete resigned.fresh_until;
    const digest = createHash('sha256')
      .update(canonicalEgressReceiptPayload(resigned))
      .digest('hex');
    resigned.receipt_digest = `sha256:${digest}`;
    resigned.receipt_signature = sign(
      null,
      Buffer.from(resigned.receipt_digest, 'utf8'),
      privateKey,
    ).toString('base64url');
    await expect(parseEgressReport(resigned, NOW)).resolves.toMatchObject({
      kind: 'stale',
      code: 'FRESHNESS_MISSING',
      lastMeasuredAt: '2026-07-27T01:00:20Z',
    });

    const invalid = { ...resigned, measured_at: '2026-02-30T00:00:00Z' };
    expect(await errorCode(invalid)).toBe('SCHEMA_INVALID');
    expect(await errorCode({ ...resigned, extra: true })).toBe('SCHEMA_INVALID');
  });

  it('classifies an expired, fully verified receipt as stale', async () => {
    await expect(parseEgressReport(
      signedReport({ fresh_until: '2026-07-27T01:00:20Z' }),
      NOW,
    )).resolves.toMatchObject({
      kind: 'stale',
      code: 'FRESHNESS_EXPIRED',
    });
  });

  it('accepts a consistent positive FAIL report', async () => {
    const report = await parseEgressReport(signedReport({
      verdict: 'FAIL',
      egress_bytes_total: 512,
      external_request_count: 1,
    }), NOW);
    expect('kind' in report).toBe(false);
    if (!('kind' in report)) expect(report.egressBytesTotal).toBe(512);
  });

  it('rejects body, digest, signature and trust-key tampering', async () => {
    const bodyTamper = signedReport();
    bodyTamper.egress_bytes_total = 1;
    bodyTamper.value = 1;
    bodyTamper.external_request_count = 1;
    bodyTamper.verdict = 'FAIL';
    expect(await errorCode(bodyTamper)).toBe('RECEIPT_UNBOUND');

    const digestTamper = signedReport();
    digestTamper.receipt_digest = `sha256:${'f'.repeat(64)}`;
    expect(await errorCode(digestTamper)).toBe('RECEIPT_UNBOUND');

    const signatureTamper = signedReport();
    signatureTamper.receipt_signature =
      `${signatureTamper.receipt_signature.startsWith('A') ? 'B' : 'A'}${signatureTamper.receipt_signature.slice(1)}`;
    expect(await errorCode(signatureTamper)).toBe('RECEIPT_UNBOUND');

    expect(await errorCode(signedReport({
      receipt_key_id: 'unknown-egress-key',
    }))).toBe('RECEIPT_UNBOUND');
  });
});
