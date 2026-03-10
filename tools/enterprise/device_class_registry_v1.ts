'use strict';

// P25-ENT-P0-02 / P25-ENT-H1: DEVICE_CLASS_REGISTRY_V1
// power_class canonical: 'high' | 'mid' | 'low' only ('medium' is INVALID)

import type { PowerClass } from '../device-profile/thermal_profile_v1';

export interface DeviceClassSlo {
  metric: string;
  threshold: number;
  operator: '>=' | '<=' | '>' | '<' | '==';
}

export interface DeviceClassEntry {
  device_class_id: string;
  display_name: string;
  min_ram_mb: number;
  backend_preferred: string;
  power_class: PowerClass;
  slo: DeviceClassSlo;
  note?: string;
}

export interface DeviceClassRegistryV1 {
  schema_version: number;
  registry_id: string;
  description: string;
  device_classes: DeviceClassEntry[];
  status: string;
}

/** Canonical power class values. 'medium' is NOT valid — use 'mid'. */
const VALID_POWER_CLASSES: readonly PowerClass[] = ['high', 'mid', 'low'];

/**
 * Look up a device class entry by ID.
 * Returns undefined if not found.
 */
export function getDeviceClass(
  registry: DeviceClassRegistryV1,
  device_class_id: string
): DeviceClassEntry | undefined {
  return registry.device_classes.find(c => c.device_class_id === device_class_id);
}

/**
 * Assert that a pack_id is allowed for the given device class entry.
 * allowed_pack_ids is an optional field — absent or empty means all packs allowed.
 * @throws Error('DEVICE_CLASS_PACK_NOT_ALLOWED') if pack is explicitly blocked.
 */
export function assertPackAllowedForDeviceClass(
  entry: DeviceClassEntry,
  pack_id: string
): void {
  // allowed_pack_ids 없으면 모든 pack 허용 (선택 필드)
  if (!('allowed_pack_ids' in entry)) return;
  const allowed = (entry as unknown as Record<string, string[] | undefined>)['allowed_pack_ids'];
  if (!allowed || allowed.length === 0) return;
  if (!allowed.includes(pack_id)) {
    throw new Error(`DEVICE_CLASS_PACK_NOT_ALLOWED:${entry.device_class_id}:${pack_id}`);
  }
}

/**
 * Assert that a DeviceClassRegistryV1 document is valid:
 * - device_classes is a non-empty array
 * - each entry has required fields: device_class_id, min_ram_mb, backend_preferred, slo
 * - power_class (if present) must be 'high' | 'mid' | 'low' — 'medium' is BLOCKED
 */
export function assertDeviceClassRegistryV1(doc: unknown): asserts doc is DeviceClassRegistryV1 {
  if (!doc || typeof doc !== 'object') {
    throw new TypeError('DEVICE_CLASS_REGISTRY_V1_NOT_OBJECT');
  }
  const obj = doc as Record<string, unknown>;
  if (!Array.isArray(obj['device_classes']) || obj['device_classes'].length === 0) {
    throw new Error('DEVICE_CLASS_REGISTRY_EMPTY_OR_MISSING');
  }
  const requiredFields = ['device_class_id', 'min_ram_mb', 'backend_preferred', 'slo', 'power_class'];
  for (const entry of obj['device_classes'] as unknown[]) {
    if (!entry || typeof entry !== 'object') {
      throw new TypeError('DEVICE_CLASS_ENTRY_NOT_OBJECT');
    }
    const e = entry as Record<string, unknown>;
    for (const field of requiredFields) {
      if (e[field] === undefined || e[field] === null) {
        throw new Error(`DEVICE_CLASS_ENTRY_FIELD_MISSING:${field}`);
      }
    }
    // power_class 값 검증: 'medium' 은 BLOCKED, 'high' | 'mid' | 'low' 만 허용
    const pc = e['power_class'] as string;
    if (pc === 'medium') {
      throw new Error(`DEVICE_CLASS_POWER_CLASS_DRIFT:${e['device_class_id']}:found=medium,expected=mid`);
    }
    if (!(VALID_POWER_CLASSES as readonly string[]).includes(pc)) {
      throw new Error(`DEVICE_CLASS_INVALID_POWER_CLASS:${e['device_class_id']}:${pc}`);
    }
  }
}

/**
 * Assert that a device_class_id string is a known registered ID.
 */
export function assertDeviceClassId(
  registry: DeviceClassRegistryV1,
  device_class_id: string
): void {
  const entry = getDeviceClass(registry, device_class_id);
  if (!entry) {
    throw new Error(`DEVICE_CLASS_NOT_FOUND:${device_class_id}`);
  }
}
