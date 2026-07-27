import { useCallback, useEffect, useReducer, useRef } from 'react';
import { sidecarFetch } from './sidecarFetch';

export type EgressReport = Readonly<{
  schemaVersion: 'butler.egress.report.v3';
  measurement: 'MEASURED';
  value: number;
  runId: string;
  measurementGeneration: number;
  measurementStartedAt: string;
  measuredAt: string;
  freshUntil: string;
  egressBytesTotal: number;
  externalRequestCount: number;
  rawFileSentExternal: boolean;
  verdict: 'PASS' | 'FAIL';
  receiptRunId: string;
  receiptKeyId: string;
  receiptAlgorithm: 'Ed25519';
  receiptPolicyVersion: string;
  receiptDigest: `sha256:${string}`;
  receiptSignature: string;
}>;

export type EgressErrorCode =
  | 'HTTP_ERROR'
  | 'INVALID_CONTENT_TYPE'
  | 'INVALID_JSON'
  | 'SCHEMA_INVALID'
  | 'UNSUPPORTED_SCHEMA'
  | 'INCONSISTENT_REPORT'
  | 'CLOCK_INVALID'
  | 'RECEIPT_UNBOUND'
  | 'MEASUREMENT_REPLAY';

export type EgressUiState =
  | Readonly<{ kind: 'loading'; generation: number }>
  | Readonly<{
      kind: 'unmeasured';
      generation: number;
      source: 'STATIC_BETA' | 'INCOMPLETE_RUNTIME' | 'UNAVAILABLE';
      lastReportedAt?: string;
    }>
  | Readonly<{ kind: 'ready'; generation: number; report: EgressReport }>
  | Readonly<{
      kind: 'stale';
      generation: number;
      lastMeasuredAt?: string;
      code: 'FRESHNESS_EXPIRED' | 'FRESHNESS_MISSING';
    }>
  | Readonly<{ kind: 'error'; generation: number; code: EgressErrorCode }>;

export type EgressReceiptTrust = Readonly<{
  keyId: string;
  publicKeySpkiBase64: string;
}>;

type EgressParseState =
  | Readonly<{
      kind: 'unmeasured';
      source: 'STATIC_BETA' | 'INCOMPLETE_RUNTIME';
      lastReportedAt?: string;
    }>
  | Readonly<{
      kind: 'stale';
      lastMeasuredAt?: string;
      code: 'FRESHNESS_EXPIRED' | 'FRESHNESS_MISSING';
    }>;

type RawReport = {
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

const REQUIRED_KEYS = [
  'schema_version',
  'measurement',
  'value',
  'run_id',
  'measurement_generation',
  'measurement_started_at',
  'measured_at',
  'fresh_until',
  'egress_bytes_total',
  'external_request_count',
  'raw_file_sent_external',
  'verdict',
  'receipt_run_id',
  'receipt_key_id',
  'receipt_algorithm',
  'receipt_policy_version',
  'receipt_digest',
  'receipt_signature',
] as const;

const RUN_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const RECEIPT_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const POLICY_VERSION = /^[A-Za-z0-9._:-]{1,64}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ED25519_SIGNATURE = /^[A-Za-z0-9_-]{86}$/;
const RFC3339_UTC =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$/;
const MAX_REPORT_WINDOW_MS = 10 * 60 * 1000;
const MAX_CLOCK_LEAD_MS = 30 * 1000;

export class EgressReportError extends Error {
  constructor(readonly code: EgressErrorCode) {
    super(code);
    this.name = 'EgressReportError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireTimestamp(value: unknown): { text: string; time: number } {
  if (typeof value !== 'string' || value.length > 30) {
    throw new EgressReportError('SCHEMA_INVALID');
  }
  const match = RFC3339_UTC.exec(value);
  if (!match) throw new EgressReportError('SCHEMA_INVALID');

  const [, rawYear, rawMonth, rawDay, rawHour, rawMinute, rawSecond, fraction = ''] =
    match;
  const year = Number(rawYear);
  const month = Number(rawMonth);
  const day = Number(rawDay);
  const hour = Number(rawHour);
  const minute = Number(rawMinute);
  const second = Number(rawSecond);
  const millisecond = Number((fraction + '000').slice(0, 3));

  // Butler's bounded profile deliberately excludes leap seconds. JavaScript
  // cannot represent them without normalization, and accepting normalized
  // calendar values would weaken the signed protocol boundary.
  if (
    year < 1
    || month < 1
    || month > 12
    || day < 1
    || day > 31
    || hour > 23
    || minute > 59
    || second > 59
  ) {
    throw new EgressReportError('SCHEMA_INVALID');
  }

  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, millisecond);
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
    || date.getUTCHours() !== hour
    || date.getUTCMinutes() !== minute
    || date.getUTCSeconds() !== second
    || date.getUTCMilliseconds() !== millisecond
  ) {
    throw new EgressReportError('SCHEMA_INVALID');
  }
  return { text: value, time: date.getTime() };
}

function requireSafeCount(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw new EgressReportError('SCHEMA_INVALID');
  }
  return value as number;
}

function requirePositiveGeneration(value: unknown): number {
  const generation = requireSafeCount(value);
  if (generation === 0) throw new EgressReportError('SCHEMA_INVALID');
  return generation;
}

function defaultReceiptTrust(): EgressReceiptTrust | undefined {
  const keyId = import.meta.env.VITE_EGRESS_RECEIPT_KEY_ID?.trim();
  const publicKeySpkiBase64 =
    import.meta.env.VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64?.trim();
  if (!keyId || !publicKeySpkiBase64) return undefined;
  return { keyId, publicKeySpkiBase64 };
}

function base64Bytes(value: string): Uint8Array {
  try {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  } catch {
    throw new EgressReportError('RECEIPT_UNBOUND');
  }
}

function base64UrlBytes(value: string): Uint8Array {
  const standard = value.replaceAll('-', '+').replaceAll('_', '/');
  return base64Bytes(standard + '='.repeat((4 - (standard.length % 4)) % 4));
}

function toHex(value: ArrayBuffer): string {
  return Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, '0'))
    .join('');
}

function exactArrayBuffer(value: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(value.byteLength);
  copy.set(value);
  return copy.buffer;
}

function cryptoBytes(value: Uint8Array): BufferSource {
  // Node 20's WebCrypto rejects ArrayBuffers originating in jsdom's realm.
  // This branch also supports Electron/SSR validation without changing the
  // browser path; no Buffer polyfill or private key is shipped to Chromium.
  const nodeBuffer = (
    globalThis as typeof globalThis & {
      Buffer?: { from(input: Uint8Array): unknown };
    }
  ).Buffer;
  if (nodeBuffer) return nodeBuffer.from(value) as BufferSource;
  return exactArrayBuffer(value);
}

/**
 * Canonical report bytes owned by both the runtime producer and UI verifier.
 *
 * Only primitive, bounded fields are allowed and property order is explicit.
 * The receipt digest and signature are deliberately excluded: digest is
 * SHA-256(canonical bytes), and signature is Ed25519(digest UTF-8 bytes).
 */
export function canonicalEgressReceiptPayload(report: RawReport): Uint8Array {
  const payload: Record<string, unknown> = {
    schema_version: report.schema_version,
    measurement: report.measurement,
    value: report.value,
    run_id: report.run_id,
    measurement_generation: report.measurement_generation,
    measurement_started_at: report.measurement_started_at,
    measured_at: report.measured_at,
  };
  if (report.fresh_until !== undefined) payload.fresh_until = report.fresh_until;
  Object.assign(payload, {
    egress_bytes_total: report.egress_bytes_total,
    external_request_count: report.external_request_count,
    raw_file_sent_external: report.raw_file_sent_external,
    verdict: report.verdict,
    receipt_run_id: report.receipt_run_id,
    receipt_key_id: report.receipt_key_id,
    receipt_algorithm: report.receipt_algorithm,
    receipt_policy_version: report.receipt_policy_version,
  });
  return new TextEncoder().encode(JSON.stringify(payload));
}

async function verifyReceipt(
  report: RawReport,
  trust: EgressReceiptTrust | undefined,
): Promise<void> {
  if (
    !trust
    || trust.keyId !== report.receipt_key_id
    || !globalThis.crypto?.subtle
  ) {
    throw new EgressReportError('RECEIPT_UNBOUND');
  }
  try {
    const canonical = canonicalEgressReceiptPayload(report);
    const actualDigest =
      `sha256:${toHex(await crypto.subtle.digest(
        'SHA-256',
        cryptoBytes(canonical),
      ))}` as const;
    if (actualDigest !== report.receipt_digest) {
      throw new EgressReportError('RECEIPT_UNBOUND');
    }
    const publicKey = await crypto.subtle.importKey(
      'spki',
      cryptoBytes(base64Bytes(trust.publicKeySpkiBase64)),
      { name: 'Ed25519' },
      false,
      ['verify'],
    );
    const valid = await crypto.subtle.verify(
      { name: 'Ed25519' },
      publicKey,
      cryptoBytes(base64UrlBytes(report.receipt_signature)),
      cryptoBytes(new TextEncoder().encode(report.receipt_digest)),
    );
    if (!valid) throw new EgressReportError('RECEIPT_UNBOUND');
  } catch (error) {
    if (error instanceof EgressReportError) throw error;
    throw new EgressReportError('RECEIPT_UNBOUND');
  }
}

export async function parseEgressReport(
  value: unknown,
  nowMs = Date.now(),
  trust = defaultReceiptTrust(),
): Promise<EgressReport | EgressParseState> {
  if (!isRecord(value)) throw new EgressReportError('SCHEMA_INVALID');
  if (value.measurement === 'STATIC_BETA') {
    const keys = Object.keys(value);
    if (
      keys.length !== 3
      || !keys.includes('value')
      || !keys.includes('measurement')
      || !keys.includes('measured_at')
    ) {
      throw new EgressReportError('SCHEMA_INVALID');
    }
    requireSafeCount(value.value);
    const reportedAt = value.measured_at === null
      ? undefined
      : requireTimestamp(value.measured_at).text;
    return {
      kind: 'unmeasured',
      source: 'STATIC_BETA',
      lastReportedAt: reportedAt,
    };
  }
  if (value.measurement === 'RUNTIME_REAL') {
    return {
      kind: 'unmeasured',
      source: 'INCOMPLETE_RUNTIME',
    };
  }
  if (value.schema_version !== 'butler.egress.report.v3') {
    throw new EgressReportError('UNSUPPORTED_SCHEMA');
  }

  const freshnessMissing = !('fresh_until' in value);
  const expectedKeys = freshnessMissing
    ? REQUIRED_KEYS.filter(key => key !== 'fresh_until')
    : [...REQUIRED_KEYS];
  const keys = Object.keys(value);
  if (
    keys.length !== expectedKeys.length
    || expectedKeys.some(key => !(key in value))
  ) {
    throw new EgressReportError('SCHEMA_INVALID');
  }
  if (
    typeof value.run_id !== 'string'
    || !RUN_ID.test(value.run_id)
    || typeof value.receipt_run_id !== 'string'
    || !RUN_ID.test(value.receipt_run_id)
    || typeof value.receipt_key_id !== 'string'
    || !RECEIPT_ID.test(value.receipt_key_id)
    || value.receipt_algorithm !== 'Ed25519'
    || typeof value.receipt_policy_version !== 'string'
    || !POLICY_VERSION.test(value.receipt_policy_version)
    || typeof value.receipt_digest !== 'string'
    || !DIGEST.test(value.receipt_digest)
    || typeof value.receipt_signature !== 'string'
    || !ED25519_SIGNATURE.test(value.receipt_signature)
    || value.measurement !== 'MEASURED'
    || typeof value.raw_file_sent_external !== 'boolean'
    || (value.verdict !== 'PASS' && value.verdict !== 'FAIL')
  ) {
    throw new EgressReportError('SCHEMA_INVALID');
  }

  const generation = requirePositiveGeneration(value.measurement_generation);
  const started = requireTimestamp(value.measurement_started_at);
  const measured = requireTimestamp(value.measured_at);
  const fresh = freshnessMissing ? undefined : requireTimestamp(value.fresh_until);
  const bytes = requireSafeCount(value.egress_bytes_total);
  const reportedValue = requireSafeCount(value.value);
  const requests = requireSafeCount(value.external_request_count);

  if (value.receipt_run_id !== value.run_id) {
    throw new EgressReportError('RECEIPT_UNBOUND');
  }
  if (
    !Number.isFinite(nowMs)
    || started.time > measured.time
    || measured.time - nowMs > MAX_CLOCK_LEAD_MS
    || (
      fresh !== undefined
      && (
        measured.time > fresh.time
        || fresh.time - measured.time > MAX_REPORT_WINDOW_MS
      )
    )
  ) {
    throw new EgressReportError('CLOCK_INVALID');
  }

  const observedExternal =
    bytes > 0 || requests > 0 || value.raw_file_sent_external;
  if (
    reportedValue !== bytes
    ||
    (value.verdict === 'PASS' && observedExternal)
    || (value.verdict === 'FAIL' && !observedExternal)
  ) {
    throw new EgressReportError('INCONSISTENT_REPORT');
  }

  const raw = value as RawReport;
  await verifyReceipt(raw, trust);

  if (fresh === undefined) {
    return {
      kind: 'stale',
      lastMeasuredAt: measured.text,
      code: 'FRESHNESS_MISSING',
    };
  }
  if (nowMs > fresh.time) {
    return {
      kind: 'stale',
      lastMeasuredAt: measured.text,
      code: 'FRESHNESS_EXPIRED',
    };
  }

  return Object.freeze({
    schemaVersion: 'butler.egress.report.v3',
    measurement: 'MEASURED',
    value: reportedValue,
    runId: raw.run_id,
    measurementGeneration: generation,
    measurementStartedAt: started.text,
    measuredAt: measured.text,
    freshUntil: fresh.text,
    egressBytesTotal: bytes,
    externalRequestCount: requests,
    rawFileSentExternal: raw.raw_file_sent_external,
    verdict: raw.verdict,
    receiptRunId: raw.receipt_run_id,
    receiptKeyId: raw.receipt_key_id,
    receiptAlgorithm: raw.receipt_algorithm,
    receiptPolicyVersion: raw.receipt_policy_version,
    receiptDigest: raw.receipt_digest,
    receiptSignature: raw.receipt_signature,
  });
}

type Action =
  | { type: 'loading'; generation: number }
  | { type: 'resolved'; generation: number; state: EgressUiState };

function reducer(state: EgressUiState, action: Action): EgressUiState {
  if (action.generation < state.generation) return state;
  if (action.type === 'loading') {
    return { kind: 'loading', generation: action.generation };
  }
  return action.state;
}

export function useEgressReport() {
  const generation = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const acceptedMeasurementGenerations = useRef(new Map<string, number>());
  const [state, dispatch] = useReducer(reducer, {
    kind: 'loading',
    generation: 0,
  });

  const refresh = useCallback(async () => {
    const nextGeneration = generation.current + 1;
    generation.current = nextGeneration;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    dispatch({ type: 'loading', generation: nextGeneration });

    let next: EgressUiState;
    try {
      const response = await sidecarFetch('/api/egress/report', {
        signal: controller.signal,
      });
      if (response.status === 503) {
        next = {
          kind: 'unmeasured',
          generation: nextGeneration,
          source: 'STATIC_BETA',
        };
        if (nextGeneration === generation.current) {
          dispatch({ type: 'resolved', generation: nextGeneration, state: next });
        }
        return;
      }
      if (!response.ok) throw new EgressReportError('HTTP_ERROR');
      const contentType = response.headers.get('content-type') ?? '';
      if (!/^application\/json(?:;|$)/i.test(contentType)) {
        throw new EgressReportError('INVALID_CONTENT_TYPE');
      }
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        throw new EgressReportError('INVALID_JSON');
      }
      const parsed = await parseEgressReport(payload);
      if ('kind' in parsed) {
        next = parsed.kind === 'unmeasured'
          ? {
              kind: 'unmeasured',
              generation: nextGeneration,
              source: parsed.source,
              lastReportedAt: parsed.lastReportedAt,
            }
          : {
              kind: 'stale',
              generation: nextGeneration,
              code: parsed.code,
              lastMeasuredAt: parsed.lastMeasuredAt,
            };
      } else {
        const previousGeneration =
          acceptedMeasurementGenerations.current.get(parsed.runId);
        if (
          previousGeneration !== undefined
          && parsed.measurementGeneration <= previousGeneration
        ) {
          throw new EgressReportError('MEASUREMENT_REPLAY');
        }
        if (
          controller.signal.aborted
          || nextGeneration !== generation.current
        ) {
          return;
        }
        acceptedMeasurementGenerations.current.set(
          parsed.runId,
          parsed.measurementGeneration,
        );
        next = { kind: 'ready', generation: nextGeneration, report: parsed };
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      next = {
        kind: 'error',
        generation: nextGeneration,
        code: error instanceof EgressReportError ? error.code : 'HTTP_ERROR',
      };
    }
    if (nextGeneration === generation.current) {
      dispatch({ type: 'resolved', generation: nextGeneration, state: next });
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => abort.current?.abort();
  }, [refresh]);

  return { state, refresh } as const;
}

export function isVerifiedZero(report: EgressReport): boolean {
  return report.measurement === 'MEASURED'
    && report.value === 0
    && report.egressBytesTotal === 0
    && report.externalRequestCount === 0
    && report.rawFileSentExternal === false
    && report.verdict === 'PASS'
    && report.receiptRunId === report.runId;
}
