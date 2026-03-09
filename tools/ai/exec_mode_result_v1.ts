'use strict';

// P22-AI-06 / P23-P0B-04: EXEC_MODE_AI_QUALITY_GATES_V2 + EXEC_FINGERPRINT_IDENTITY_SPLIT_V1

import { typedDigest } from '../crypto/digest_v1';

/**
 * Identity material for a logical model pack + execution config.
 * Used to compute pack_identity_digest and exec_fingerprint_sha256.
 */
export interface ExecIdentityMaterial {
  pack_id: string;
  model_manifest_digest_sha256: string;
  tokenizer_digest_sha256: string;
  config_digest_sha256: string;
  runtime_id: string;
  runtime_config_digest_sha256: string;
  input_digest_sha256: string;
  output_digest_sha256: string;
  decode_params_digest_sha256: string;
  policy_version: string;
}

/**
 * On-device execution performance observation.
 * CPU/latency stored as string (bigint serialization) at source; display fields are ms.
 */
export interface ExecObservation {
  /** CPU time (user + system) in microseconds, as string (bigint → JSON) */
  cpu_time_us: string;
  /** Wall-clock latency in nanoseconds, as string (bigint → JSON) */
  latency_ns: string;
  /** Display value: cpu_time_us / 1000 */
  cpu_time_ms_display: number;
  /** Display value: latency_ns / 1_000_000 */
  latency_ms_display: number;
  /** Quality proxy score in [0, 1] */
  quality_proxy_score: number;
}

/**
 * ExecModeResultV3: output of a single on-device inference run.
 * routing_decision_digest: deterministic (same decision → same digest, no timestamp).
 * routing_event_id: unique per invocation (includes timestamp_ns).
 * pack_identity_digest: based on logical_model_pack fields only.
 * exec_fingerprint_sha256: based on full ExecIdentityMaterial (input+config+output).
 */
export interface ExecModeResultV3 {
  pack_id: string;
  device_class_id: string;
  reason_code: string;

  routing_decision_digest: string;
  routing_event_id: string;

  chain_proof_digest: string;
  /** Digest of pack identity (pack_id, manifest, tokenizer, config, runtime) */
  pack_identity_digest: string;
  /** Digest of full execution identity (input + config + output) */
  exec_fingerprint_sha256: string;

  observation: ExecObservation;
}

/**
 * Build a pack identity digest from logical model pack fields.
 * Deterministic: does not include runtime inputs/outputs.
 */
export function buildPackIdentityDigest(m: Pick<ExecIdentityMaterial,
  'pack_id' | 'model_manifest_digest_sha256' | 'tokenizer_digest_sha256' | 'config_digest_sha256' | 'runtime_id'>
): string {
  return typedDigest('pack-identity', 'v1', m);
}

/**
 * Build the exec fingerprint from full identity material.
 * Covers: pack identity + runtime config + input + output + decode params.
 */
export function buildExecFingerprintSha256(m: ExecIdentityMaterial): string {
  return typedDigest('exec-fingerprint', 'v1', m);
}

/**
 * Assert that r is a valid ExecModeResultV3 with all required fields.
 */
export function assertExecModeResultV3(r: unknown): asserts r is ExecModeResultV3 {
  if (!r || typeof r !== 'object') {
    throw new TypeError('ExecModeResultV3 must be a non-null object');
  }
  const required = [
    'pack_id', 'device_class_id', 'reason_code',
    'routing_decision_digest', 'routing_event_id',
    'chain_proof_digest', 'pack_identity_digest', 'exec_fingerprint_sha256',
    'observation',
  ];
  for (const k of required) {
    if (!(r as Record<string, unknown>)[k]) {
      throw new Error(`EXEC_RESULT_MISSING_FIELD:${k}`);
    }
  }
}

/**
 * Check that a value is a valid lowercase hex SHA-256 string (64 chars).
 */
export function isValidSha256Hex(value: string): boolean {
  return /^[0-9a-f]{64}$/.test(value);
}
