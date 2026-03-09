'use strict';

// P23-P1-01: THERMAL_ENERGY_PROFILE_V1

export type ThermalState = 'nominal' | 'fair' | 'serious' | 'critical';
export type BatteryBucket = 'ok' | 'low' | 'critical';
export type PowerClass = 'low' | 'mid' | 'high';

export interface ThermalEnergyProfile {
  thermal_headroom: number;       // 0.0~1.0 (1.0=여유 최대)
  thermal_state: ThermalState;
  low_power_mode: boolean;
  battery_bucket: BatteryBucket;
  sustained_perf_available: boolean;
}

export function classifyThermalState(headroom: number): ThermalState {
  if (headroom >= 0.7) return 'nominal';
  if (headroom >= 0.4) return 'fair';
  if (headroom >= 0.2) return 'serious';
  return 'critical';
}

export function isSustainedPerfAvailable(profile: ThermalEnergyProfile): boolean {
  return (
    profile.thermal_state === 'nominal' &&
    !profile.low_power_mode &&
    profile.battery_bucket === 'ok'
  );
}

export function mockThermalProfile(): ThermalEnergyProfile {
  return {
    thermal_headroom: 0.8,
    thermal_state: 'nominal',
    low_power_mode: false,
    battery_bucket: 'ok',
    sustained_perf_available: true,
  };
}
