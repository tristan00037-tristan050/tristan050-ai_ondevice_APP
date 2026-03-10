// AI-ALGO: DEVICE_PROBE_CONTRACT_V1
// 알고리즘팀 산출물 — 알고리즘팀 전용 기기 probe 계약 (probe_model_digest 포함)

import { typedDigest } from '../crypto/digest_v1.ts';

export interface AlgoDeviceProbeContractV1 {
  probe_model_digest_sha256: string;
  probe_schema_version: number;
  required_fields: string[];
  thermal_states: string[];
  backends: string[];
}

export const ALGO_DEVICE_PROBE_CONTRACT_V1: AlgoDeviceProbeContractV1 = {
  probe_model_digest_sha256: 'PENDING_REAL_WEIGHTS',
  probe_schema_version: 1,
  required_fields: [
    'probe_id',
    'probe_digest',
    'device_fingerprint_digest',
    'available_ram_mb',
    'cpu_single_score',
    'has_gpu',
    'has_npu',
    'thermal_state',
    'backend',
    'probe_timestamp_utc',
  ],
  thermal_states: ['nominal', 'warm', 'hot', 'critical'],
  backends: ['cpu', 'cuda', 'metal', 'nnapi'],
};

export interface AlgoProbeResultMaterialV1 {
  probe_schema_version: number;
  device_fingerprint_digest: string;
  available_ram_mb: number;
  cpu_single_score: number;
  has_gpu: boolean;
  has_npu: boolean;
  thermal_state: string;
  backend: string;
}

export function buildAlgoProbeDigestV1(material: AlgoProbeResultMaterialV1): string {
  return typedDigest('algo-device-probe', 'v1', material);
}

export function assertAlgoDeviceProbeContractV1(c: unknown): asserts c is AlgoDeviceProbeContractV1 {
  if (!c || typeof c !== 'object') throw new Error('ALGO_DEVICE_PROBE_CONTRACT_NOT_OBJECT');
  const p = c as Record<string, unknown>;
  if (typeof p['probe_model_digest_sha256'] !== 'string' || !p['probe_model_digest_sha256'])
    throw new Error('ALGO_DEVICE_PROBE_CONTRACT_MISSING:probe_model_digest_sha256');
  if (typeof p['probe_schema_version'] !== 'number')
    throw new Error('ALGO_DEVICE_PROBE_CONTRACT_MISSING:probe_schema_version');
}
