'use strict';

// P25-ENT-P0-02: DEVICE_CLASS_REGISTRY_V1

import type { PowerClass } from '../device-profile/thermal_profile_v1';

export interface DeviceClassEntry {
  device_class_id: string;
  display_name: string;
  min_ram_gb: number;
  min_npu_tops: number;
  allowed_pack_ids: string[];
  power_class: PowerClass;
  note?: string;
}

export interface DeviceClassRegistryV1 {
  schema_version: number;
  registry_id: string;
  description: string;
  device_classes: DeviceClassEntry[];
  status: string;
}

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
 * Assert that a pack_id is allowed for the given device class.
 * @throws Error('DEVICE_CLASS_PACK_NOT_ALLOWED') if the pack is not in allowed_pack_ids.
 * @throws Error('DEVICE_CLASS_NOT_FOUND') if the device_class_id doesn't exist.
 */
export function assertPackAllowedForDeviceClass(
  registry: DeviceClassRegistryV1,
  device_class_id: string,
  pack_id: string
): void {
  const entry = getDeviceClass(registry, device_class_id);
  if (!entry) {
    throw new Error(`DEVICE_CLASS_NOT_FOUND:${device_class_id}`);
  }
  if (!entry.allowed_pack_ids.includes(pack_id)) {
    throw new Error(`DEVICE_CLASS_PACK_NOT_ALLOWED:${device_class_id}:${pack_id}`);
  }
}

/**
 * Assert that a DeviceClassRegistryV1 document is valid:
 * - device_classes is a non-empty array
 * - each entry has required fields
 */
export function assertDeviceClassRegistryV1(doc: unknown): asserts doc is DeviceClassRegistryV1 {
  if (!doc || typeof doc !== 'object') {
    throw new TypeError('DEVICE_CLASS_REGISTRY_V1_NOT_OBJECT');
  }
  const obj = doc as Record<string, unknown>;
  if (!Array.isArray(obj['device_classes']) || obj['device_classes'].length === 0) {
    throw new Error('DEVICE_CLASS_REGISTRY_EMPTY_OR_MISSING');
  }
  const requiredFields = ['device_class_id', 'display_name', 'min_ram_gb', 'min_npu_tops', 'allowed_pack_ids', 'power_class'];
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
    if (!Array.isArray(e['allowed_pack_ids']) || e['allowed_pack_ids'].length === 0) {
      throw new Error(`DEVICE_CLASS_ENTRY_ALLOWED_PACKS_EMPTY:${e['device_class_id']}`);
    }
  }
}
