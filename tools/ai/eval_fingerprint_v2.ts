// AI-ALGO: EVAL_FINGERPRINT_V2
// 알고리즘팀 산출물 — EvalFingerprintV2 (schema_pass_rate >= 0.98, violation_rate <= 0.01)

import { typedDigest } from '../crypto/digest_v1.ts';

export interface EvalFingerprintV2 {
  logical_pack_id: string;
  eval_corpus_digest_sha256: string;
  schema_pass_rate: number;
  violation_rate: number;
  sample_count: number;
  eval_timestamp_utc: string;
  fingerprint_digest: string;
}

export interface EvalFingerprintMaterialV2 {
  logical_pack_id: string;
  eval_corpus_digest_sha256: string;
  schema_pass_rate: number;
  violation_rate: number;
  sample_count: number;
}

export function buildEvalFingerprintV2(material: EvalFingerprintMaterialV2, eval_timestamp_utc: string): EvalFingerprintV2 {
  const fingerprint_digest = typedDigest('eval-fingerprint', 'v2', material);
  return {
    ...material,
    eval_timestamp_utc,
    fingerprint_digest,
  };
}

export function assertEvalFingerprintV2(f: unknown): asserts f is EvalFingerprintV2 {
  if (!f || typeof f !== 'object') throw new Error('EVAL_FINGERPRINT_V2_NOT_OBJECT');
  const e = f as Record<string, unknown>;
  if (typeof e['logical_pack_id'] !== 'string' || !e['logical_pack_id'])
    throw new Error('EVAL_FINGERPRINT_V2_MISSING:logical_pack_id');
  if (typeof e['schema_pass_rate'] !== 'number')
    throw new Error('EVAL_FINGERPRINT_V2_MISSING:schema_pass_rate');
  if ((e['schema_pass_rate'] as number) < 0.98)
    throw new Error(`EVAL_FINGERPRINT_V2_SCHEMA_PASS_RATE_BELOW_THRESHOLD:${e['schema_pass_rate']}`);
  if (typeof e['violation_rate'] !== 'number')
    throw new Error('EVAL_FINGERPRINT_V2_MISSING:violation_rate');
  if ((e['violation_rate'] as number) > 0.01)
    throw new Error(`EVAL_FINGERPRINT_V2_VIOLATION_RATE_ABOVE_THRESHOLD:${e['violation_rate']}`);
  if (typeof e['sample_count'] !== 'number' || (e['sample_count'] as number) < 30)
    throw new Error(`EVAL_FINGERPRINT_V2_SAMPLE_COUNT_TOO_LOW:${e['sample_count']}`);
  if (typeof e['fingerprint_digest'] !== 'string' || !/^[0-9a-f]{64}$/.test(e['fingerprint_digest'] as string))
    throw new Error('EVAL_FINGERPRINT_V2_INVALID:fingerprint_digest');
}
