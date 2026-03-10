'use strict';

// AI-P3-06: DEVICE_PROBE_AND_CLASSIFY_V1

import { cpuUsage, hrtime } from 'node:process';
import { typedDigest } from '../crypto/digest_v1';

export function nowNs(): bigint { return hrtime.bigint(); }

export function cpuTimeMsDelta(
  prev: NodeJS.CpuUsage,
  next: NodeJS.CpuUsage
): number {
  const totalUs = (next.user - prev.user) + (next.system - prev.system);
  if (totalUs < 0) throw new Error('CPU_TIME_NEGATIVE_DELTA');
  return totalUs / 1000.0;
}

export interface DeviceProbeResultV1 {
  schema_version: 1;
  measured_at_utc: string;
  cpu_single_score: number;        // 정규화 0~100
  available_ram_mb: number;
  has_gpu: boolean;
  has_npu: boolean;
  thermal_state: 'nominal' | 'fair' | 'serious' | 'critical';
  ttft_ms?: number;
  decode_tps?: number;
  peak_rss_mb?: number;
  probe_digest: string;            // probe 결과 canonical digest
}

export interface DeviceClassDecisionV1 {
  registry_version: string;
  probe_digest: string;
  device_class_id: string;
  classification_reason_code:
    | 'HIGH_RAM_HIGH_CPU'
    | 'MID_RAM_CPU'
    | 'NPU_MOBILE'
    | 'GPU_DESKTOP'
    | 'THERMAL_LIMITED';
}

export async function runDeviceProbeV1(): Promise<DeviceProbeResultV1> {
  const cpuBefore = cpuUsage();
  const t0 = hrtime.bigint();

  // 100ms 연산 벤치마크
  let sum = 0;
  for (let i = 0; i < 10_000_000; i++) sum += Math.sqrt(i);

  const elapsed_ms = Number(hrtime.bigint() - t0) / 1_000_000;
  const cpuAfter = cpuUsage();
  void sum;
  void cpuBefore;
  void cpuAfter;

  const cpu_single_score = Math.min(100, (10_000_000 / elapsed_ms) / 1000);

  // available_ram_mb
  const available_ram_mb = (process as Record<string, unknown>)['availableMemory']
    ? ((process as Record<string, () => number>)['availableMemory']()) / (1024 * 1024)
    : 8192;

  const result: Omit<DeviceProbeResultV1, 'probe_digest'> = {
    schema_version: 1,
    measured_at_utc: new Date().toISOString(),
    cpu_single_score: Math.round(cpu_single_score * 100) / 100,
    available_ram_mb: Math.round(available_ram_mb),
    has_gpu: false,
    has_npu: false,
    thermal_state: 'nominal',
  };

  // probe_digest: canonical SHA-256 (typedDigest 사용)
  const probe_digest = typedDigest('device-probe', 'v1', result);

  return { ...result, probe_digest };
}

export function classifyDeviceV1(
  probe: DeviceProbeResultV1,
  registryVersion: string
): DeviceClassDecisionV1 {
  // thermal_state=critical 시 THERMAL_LIMITED 마킹
  // device_class_id는 변경하지 않음 (플랫폼팀 원칙)
  if (probe.thermal_state === 'critical') {
    return {
      registry_version: registryVersion,
      probe_digest: probe.probe_digest,
      device_class_id: 'laptop_cpu',  // 기본값 유지
      classification_reason_code: 'THERMAL_LIMITED',
    };
  }

  let device_class_id: string;
  let classification_reason_code: DeviceClassDecisionV1['classification_reason_code'];

  if (probe.has_npu && probe.available_ram_mb < 6144) {
    device_class_id = 'phone_npu';
    classification_reason_code = 'NPU_MOBILE';
  } else if (probe.has_gpu && probe.available_ram_mb >= 8192) {
    device_class_id = 'desktop_gpu';
    classification_reason_code = 'GPU_DESKTOP';
  } else if (probe.available_ram_mb >= 8192 && probe.cpu_single_score >= 80) {
    device_class_id = 'desktop_cpu';
    classification_reason_code = 'HIGH_RAM_HIGH_CPU';
  } else if (probe.available_ram_mb >= 4096 && probe.cpu_single_score >= 50) {
    device_class_id = 'laptop_cpu';
    classification_reason_code = 'MID_RAM_CPU';
  } else {
    device_class_id = 'laptop_cpu';
    classification_reason_code = 'MID_RAM_CPU';
  }

  return {
    registry_version: registryVersion,
    probe_digest: probe.probe_digest,
    device_class_id,
    classification_reason_code,
  };
}

/**
 * Assert that r is a valid DeviceProbeResultV1.
 * Validates schema_version, numeric fields, and probe_digest SHA-256 format.
 */
export function assertDeviceProbeResultV1(r: unknown): asserts r is DeviceProbeResultV1 {
  if (!r || typeof r !== 'object') throw new TypeError('DEVICE_PROBE_NOT_OBJECT');
  const obj = r as Record<string, unknown>;
  if (obj['schema_version'] !== 1) throw new Error('DEVICE_PROBE_INVALID_SCHEMA_VERSION');
  if (typeof obj['cpu_single_score'] !== 'number') throw new Error('DEVICE_PROBE_CPU_SCORE_MISSING');
  if (typeof obj['available_ram_mb'] !== 'number') throw new Error('DEVICE_PROBE_RAM_MISSING');
  if (typeof obj['probe_digest'] !== 'string' || !/^[0-9a-f]{64}$/.test(obj['probe_digest'] as string)) {
    throw new Error('DEVICE_PROBE_DIGEST_INVALID');
  }
}

/**
 * Assert that r is a valid DeviceClassDecisionV1.
 * Validates device_class_id presence, probe_digest SHA-256 format,
 * and classification_reason_code against the canonical set.
 */
export function assertDeviceClassDecisionV1(r: unknown): asserts r is DeviceClassDecisionV1 {
  if (!r || typeof r !== 'object') throw new TypeError('DEVICE_CLASS_DECISION_NOT_OBJECT');
  const obj = r as Record<string, unknown>;
  if (typeof obj['device_class_id'] !== 'string' || (obj['device_class_id'] as string).length === 0) {
    throw new Error('DEVICE_CLASS_DECISION_ID_MISSING');
  }
  if (typeof obj['probe_digest'] !== 'string' || !/^[0-9a-f]{64}$/.test(obj['probe_digest'] as string)) {
    throw new Error('DEVICE_CLASS_DECISION_PROBE_DIGEST_INVALID');
  }
  const validReasons = [
    'HIGH_RAM_HIGH_CPU', 'MID_RAM_CPU',
    'NPU_MOBILE', 'GPU_DESKTOP', 'THERMAL_LIMITED',
  ];
  if (!validReasons.includes(obj['classification_reason_code'] as string)) {
    throw new Error(`DEVICE_CLASS_DECISION_INVALID_REASON:${obj['classification_reason_code']}`);
  }
}
