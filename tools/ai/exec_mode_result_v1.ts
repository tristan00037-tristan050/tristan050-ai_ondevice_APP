'use strict';

// P22-AI-06 / P23-P0B-04 / P23-P2B-04 / P25-ENT-H2: EXEC_MODE_AI_QUALITY_GATES_V2 + EXEC_FINGERPRINT_IDENTITY_SPLIT_V1 + EXEC_MODE_RESULT_V4 + EXEC_MODE_V4_STRICT

import { typedDigest } from '../crypto/digest_v1';

// ---------------------------------------------------------------------------
// KV Cache policy types
// ---------------------------------------------------------------------------
export type KvCacheMode = 'baseline' | 'shadow' | 'active';
export type KvPolicyId = 'none' | 'h2o';

export interface KvPolicy {
  kv_cache_mode: KvCacheMode;
  kv_policy_id: KvPolicyId;
  kv_policy_params_digest?: string;
}

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
 * ExecModeResultV4: adds enterprise org context, KV cache mode, and 3-part pack identity.
 * Extends V3 with: logical_pack_digest / compiled_pack_digest split,
 * tokenizer_template_digest, KV policy, toolcall digest, org hierarchy fields.
 */
export interface ExecModeResultV4 {
  // pack identity 3분리
  logical_pack_digest: string;
  compiled_pack_digest: string;
  pack_identity_digest: string;
  tokenizer_template_digest: string;

  // 라우팅
  routing_decision_digest: string;
  routing_event_id: string;

  // 실행 동일성
  exec_fingerprint_sha256: string;
  chain_proof_digest: string;

  // KV 캐시
  kv_cache_mode: KvCacheMode;
  kv_policy_params_digest?: string;

  // 툴콜 (optional)
  tool_schema_digest?: string;

  // 기업용 조직 컨텍스트
  principal_id: string;
  group_id?: string;
  department_id?: string;
  org_id: string;
  policy_digest: string;
  approved_pack_digest: string;
  rollout_ring: string;

  // 관측값
  observation: ExecObservation;
  device_class_id: string;
  reason_code: string;
}

/**
 * Assert that r is a valid ExecModeResultV4 with all required fields.
 * Blocks: kv_cache_mode='active' without valid kv_policy_params_digest.
 * Blocks: principal_id or org_id missing.
 */
export function assertExecModeResultV4(r: unknown): asserts r is ExecModeResultV4 {
  if (!r || typeof r !== 'object') {
    throw new TypeError('ExecModeResultV4 must be a non-null object');
  }
  const obj = r as Record<string, unknown>;
  const required = [
    'logical_pack_digest', 'compiled_pack_digest', 'pack_identity_digest',
    'tokenizer_template_digest', 'routing_decision_digest', 'routing_event_id',
    'exec_fingerprint_sha256', 'chain_proof_digest', 'kv_cache_mode',
    'principal_id', 'org_id', 'policy_digest', 'approved_pack_digest',
    'rollout_ring', 'observation', 'device_class_id', 'reason_code',
  ];
  for (const k of required) {
    if (!obj[k]) {
      throw new Error(`EXEC_V4_MISSING_FIELD:${k}`);
    }
  }
  if (!obj['principal_id']) throw new Error('EXEC_V4_MISSING_PRINCIPAL_ID');
  if (!obj['org_id']) throw new Error('EXEC_V4_MISSING_ORG_ID');

  // kv_cache_mode='active' 인데 kv_policy_params_digest 없으면 BLOCK
  if (obj['kv_cache_mode'] === 'active' && !obj['kv_policy_params_digest']) {
    throw new Error('EXEC_V4_KV_ACTIVE_WITHOUT_POLICY_PARAMS_DIGEST');
  }
}

/**
 * Build a pack identity digest from logical model pack fields (v1).
 * Deterministic: does not include runtime inputs/outputs.
 */
export function buildPackIdentityDigest(m: Pick<ExecIdentityMaterial,
  'pack_id' | 'model_manifest_digest_sha256' | 'tokenizer_digest_sha256' | 'config_digest_sha256' | 'runtime_id'>
): string {
  return typedDigest('pack-identity', 'v1', m);
}

/**
 * Build a pack identity digest v2: 3-part split (logical / compiled / tokenizer_template).
 */
export function buildPackIdentityDigestV2(m: {
  logical_pack_id: string;
  logical_pack_digest: string;
  compiled_pack_id: string;
  compiled_pack_digest: string;
  tokenizer_template_digest: string;
}): string {
  return typedDigest('pack-identity', 'v2', m);
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

// ---------------------------------------------------------------------------
// P25-ENT-H2: EXEC_MODE_V4_STRICT — SHA-256 형식 + 의미 정합 + rollout ring 유효성
// ---------------------------------------------------------------------------

/**
 * Assert that a field value is a valid lowercase hex SHA-256 string (64 chars).
 * @throws Error('EXEC_V4_INVALID_SHA256:<field>') if invalid.
 */
function assertSha256Hex(v: unknown, field: string): void {
  if (typeof v !== 'string' || !/^[0-9a-f]{64}$/.test(v)) {
    throw new Error(`EXEC_V4_INVALID_SHA256:${field}`);
  }
}

/**
 * Strict validator for ExecModeResultV4.
 * Calls assertExecModeResultV4 first (field presence), then enforces:
 * - All digest fields are valid SHA-256 hex (64-char lowercase)
 * - rollout_ring is one of the 4 canonical values
 * - routing_event_id MUST differ from routing_decision_digest
 * - kv_cache_mode='active' requires kv_policy_params_digest
 */
export function assertExecModeResultV4Strict(
  r: unknown
): asserts r is ExecModeResultV4 {
  // 기존 assertExecModeResultV4 먼저 호출 (필드 존재 확인)
  assertExecModeResultV4(r);
  const obj = r as Record<string, unknown>;

  // SHA-256 형식 검증 (64자 hex 소문자)
  for (const f of [
    'logical_pack_digest',
    'compiled_pack_digest',
    'pack_identity_digest',
    'tokenizer_template_digest',
    'routing_decision_digest',
    'routing_event_id',
    'exec_fingerprint_sha256',
    'chain_proof_digest',
    'policy_digest',
    'approved_pack_digest',
  ]) {
    assertSha256Hex(obj[f], f);
  }

  // rollout_ring 유효성 검증
  const ring = String(obj['rollout_ring']);
  if (!['ring0_canary', 'ring1_team', 'ring2_department', 'ring3_org'].includes(ring)) {
    throw new Error(`EXEC_V4_INVALID_ROLLOUT_RING:${ring}`);
  }

  // routing_event_id 와 routing_decision_digest 는 반드시 달라야 함
  if (obj['routing_event_id'] === obj['routing_decision_digest']) {
    throw new Error('EXEC_V4_ROUTING_EVENT_ID_MUST_DIFFER_FROM_DECISION_DIGEST');
  }

  // kv_cache_mode=active 인데 kv_policy_params_digest 없으면 BLOCK
  if (obj['kv_cache_mode'] === 'active' && !obj['kv_policy_params_digest']) {
    throw new Error('EXEC_V4_KV_ACTIVE_WITHOUT_POLICY_PARAMS_DIGEST');
  }
}
