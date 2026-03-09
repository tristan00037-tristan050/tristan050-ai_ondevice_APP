'use strict';

// P22-AI-06: EXEC_MODE_AI_QUALITY_GATES_V2

/**
 * ExecModeResult captures the output of a single on-device inference run,
 * including identity, performance metrics, and audit digests.
 *
 * All digest fields are SHA-256 hex strings.
 */
export interface ExecModeResult {
  /** Pack used for this inference (e.g., "micro_default") */
  pack_id: string;
  /** Device class identifier (e.g., "mobile_tier1", "desktop_tier2") */
  device_class_id: string;
  /** Routing reason code from model_router_v1 */
  reason_code: string;
  /** CPU time consumed in milliseconds (user + system) */
  cpu_time_ms: number;
  /** Quality proxy score in [0, 1] (surrogate for latency-adjusted output quality) */
  quality_proxy_score: number;
  /** SHA-256 digest of the routing log payload (audit trail for pack selection) */
  routing_log_digest: string;
  /** SHA-256 digest of the artifact chain proof at time of execution */
  chain_proof_digest: string;
  /** SHA-256 of (pack_id + device_class_id + reason_code + cpu_time_ms + quality_proxy_score) */
  exec_fingerprint_sha256: string;
}

/**
 * Validate that an ExecModeResult has all required fields with correct types.
 * Throws if invalid.
 */
export function assertExecModeResult(result: unknown): asserts result is ExecModeResult {
  if (!result || typeof result !== 'object') {
    throw new TypeError('ExecModeResult must be a non-null object');
  }
  const r = result as Record<string, unknown>;

  const stringFields = [
    'pack_id',
    'device_class_id',
    'reason_code',
    'routing_log_digest',
    'chain_proof_digest',
    'exec_fingerprint_sha256',
  ];
  for (const field of stringFields) {
    if (typeof r[field] !== 'string' || (r[field] as string).length === 0) {
      throw new TypeError(`ExecModeResult.${field} must be a non-empty string`);
    }
  }

  if (typeof r['cpu_time_ms'] !== 'number' || r['cpu_time_ms'] < 0) {
    throw new RangeError('ExecModeResult.cpu_time_ms must be a non-negative number');
  }
  if (
    typeof r['quality_proxy_score'] !== 'number' ||
    r['quality_proxy_score'] < 0 ||
    r['quality_proxy_score'] > 1
  ) {
    throw new RangeError('ExecModeResult.quality_proxy_score must be in [0, 1]');
  }
}

/**
 * Check that exec_fingerprint_sha256 is a valid lowercase hex SHA-256 string (64 chars).
 */
export function isValidSha256Hex(value: string): boolean {
  return /^[0-9a-f]{64}$/.test(value);
}
