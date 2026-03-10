'use strict';

export interface QualityGateInputV1 {
  schema_pass_rate: number;
  tool_validity_rate: number;
  violation_rate: number;
  quality_proxy_score_delta_pct: number;
}

export function assertQualityGateV1(x: QualityGateInputV1): void {
  if (x.schema_pass_rate < 0.98) {
    throw new Error(`QUALITY_GATE_SCHEMA_FAIL:${x.schema_pass_rate}`);
  }
  if (x.tool_validity_rate < 0.995) {
    throw new Error(`QUALITY_GATE_TOOL_FAIL:${x.tool_validity_rate}`);
  }
  if (x.violation_rate > 0.01) {
    throw new Error(`QUALITY_GATE_VIOLATION_FAIL:${x.violation_rate}`);
  }
  if (x.quality_proxy_score_delta_pct < -5.0) {
    throw new Error(`QUALITY_GATE_QUALITY_DROP_FAIL:${x.quality_proxy_score_delta_pct}`);
  }
}
