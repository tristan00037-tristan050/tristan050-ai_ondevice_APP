'use strict';

// P24-R-02: NATIVE_LOWBIT_MODEL_TRACK_V1
// 실험 레인 — production 라우팅에 미연결

export type QuantizationStatus =
  | 'production_primary'
  | 'production_candidate'
  | 'experimental'
  | 'research';

export interface QuantizationStrategy {
  strategy_id: string;
  method: string;
  status: QuantizationStatus;
  bits: number;
  is_production_allowed: boolean;
}

export const QUANTIZATION_REGISTRY: QuantizationStrategy[] = [
  {
    strategy_id: 'w8a8_smoothquant',
    method: 'SmoothQuant',
    status: 'production_candidate',
    bits: 8,
    is_production_allowed: true,
  },
  {
    strategy_id: 'int4_awq',
    method: 'AWQ',
    status: 'production_primary',
    bits: 4,
    is_production_allowed: true,
  },
  {
    strategy_id: 'mixed_precision_critical',
    method: 'critical_layer_fp16_exception',
    status: 'experimental',
    bits: 4,
    is_production_allowed: false,
  },
  {
    strategy_id: 'native_lowbit_bitnet',
    method: 'BitNet_b1.58',
    status: 'research',
    bits: 2,
    is_production_allowed: false,
  },
];

export function getProductionStrategies(): QuantizationStrategy[] {
  return QUANTIZATION_REGISTRY.filter(s => s.is_production_allowed);
}

export function assertNotResearchInProduction(strategy_id: string): void {
  const s = QUANTIZATION_REGISTRY.find(s => s.strategy_id === strategy_id);
  if (!s) throw new Error(`UNKNOWN_QUANTIZATION_STRATEGY:${strategy_id}`);
  if (!s.is_production_allowed) {
    throw new Error(`RESEARCH_STRATEGY_IN_PRODUCTION:${strategy_id}`);
  }
}
