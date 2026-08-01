import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import {
  canonicalEgressReceiptPayload,
  EgressReportError,
  parseEgressReport,
} from '../../lib/egressReport';

const NOW = Date.parse('2026-07-27T01:00:30Z');
const KEY_ID = 'firstscreen-v7-measurement-test';
const { privateKey, publicKey } = generateKeyPairSync('ed25519');
const trust = {
  keyId: KEY_ID,
  publicKeySpkiBase64: publicKey
    .export({ format: 'der', type: 'spki' })
    .toString('base64'),
};

type WireReport = Parameters<typeof canonicalEgressReceiptPayload>[0];

function signedReport(overrides: Partial<WireReport> = {}): WireReport {
  const report: WireReport = {
    schema_version: 'butler.egress.report.v3',
    measurement: 'MEASURED',
    value: 0,
    run_id: 'firstscreen-v7-run',
    measurement_generation: 11,
    measurement_started_at: '2026-07-27T01:00:00Z',
    measured_at: '2026-07-27T01:00:20Z',
    fresh_until: '2026-07-27T01:01:20Z',
    egress_bytes_total: 0,
    external_request_count: 0,
    raw_file_sent_external: false,
    verdict: 'PASS',
    receipt_run_id: 'firstscreen-v7-run',
    receipt_key_id: KEY_ID,
    receipt_algorithm: 'Ed25519',
    receipt_policy_version: 'egress-policy-2026.1',
    receipt_digest: `sha256:${'0'.repeat(64)}`,
    receipt_signature: 'A'.repeat(86),
    ...overrides,
  };
  report.receipt_digest = `sha256:${createHash('sha256')
    .update(canonicalEgressReceiptPayload(report))
    .digest('hex')}`;
  report.receipt_signature = sign(
    null,
    Buffer.from(report.receipt_digest, 'utf8'),
    privateKey,
  ).toString('base64url');
  return report;
}

describe('FirstScreen measured egress provenance', () => {
  it('shows zero only for a fresh verified MEASURED receipt', async () => {
    const result = await parseEgressReport(signedReport(), NOW, trust);

    expect('kind' in result).toBe(false);
    if (!('kind' in result)) {
      expect(result.measurement).toBe('MEASURED');
      expect(result.value).toBe(0);
      expect(result.receiptRunId).toBe(result.runId);
    }
  });

  it('blocks STATIC_BETA legacy stale unsigned and future-dated zero values', async () => {
    await expect(parseEgressReport({
      measurement: 'STATIC_BETA',
      value: 0,
      measured_at: null,
    }, NOW, trust)).resolves.toMatchObject({
      kind: 'unmeasured',
      source: 'STATIC_BETA',
    });
    await expect(parseEgressReport({
      schema_version: 2,
      measurement: 'UNAVAILABLE',
      generation: 12,
      run_id: null,
      value: null,
      measured_at: null,
      receipt: null,
    }, NOW, trust)).resolves.toMatchObject({
      kind: 'unmeasured',
      source: 'UNAVAILABLE',
    });
    await expect(parseEgressReport({ value: 0 }, NOW, trust)).resolves.toMatchObject({
      kind: 'unmeasured',
      source: 'UNAVAILABLE',
    });
    await expect(parseEgressReport(signedReport({
      fresh_until: '2026-07-27T01:00:29Z',
    }), NOW, trust)).resolves.toMatchObject({ kind: 'stale' });

    const unsigned = signedReport();
    unsigned.receipt_signature = 'A'.repeat(86);
    await expect(parseEgressReport(unsigned, NOW, trust)).rejects.toMatchObject({
      code: 'RECEIPT_UNBOUND',
    } satisfies Partial<EgressReportError>);

    await expect(parseEgressReport(signedReport({
      measured_at: '2026-07-27T01:01:01Z',
      fresh_until: '2026-07-27T01:02:00Z',
    }), NOW, trust)).rejects.toMatchObject({ code: 'CLOCK_INVALID' });
  });
});
