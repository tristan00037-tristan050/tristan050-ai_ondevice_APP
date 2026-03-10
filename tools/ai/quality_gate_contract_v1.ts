'use strict';

export interface QualityGateInputV1 {
  schema_pass_rate: number;
  tool_validity_rate: number;
  violation_rate: number;
  quality_proxy_score_delta_pct: number;
}

export function assertQualityGateV1(x: QualityGateInputV1): void {
  // NaN / 비숫자 입력 → 즉시 차단 (fail-closed)
  if (!Number.isFinite(x.schema_pass_rate)) {
    throw new Error(`QUALITY_GATE_SCHEMA_PASS_RATE_INVALID:${x.schema_pass_rate}`);
  }
  if (!Number.isFinite(x.tool_validity_rate)) {
    throw new Error(`QUALITY_GATE_TOOL_VALIDITY_RATE_INVALID:${x.tool_validity_rate}`);
  }
  if (!Number.isFinite(x.violation_rate)) {
    throw new Error(`QUALITY_GATE_VIOLATION_RATE_INVALID:${x.violation_rate}`);
  }
  if (!Number.isFinite(x.quality_proxy_score_delta_pct)) {
    throw new Error(`QUALITY_GATE_QUALITY_DELTA_INVALID:${x.quality_proxy_score_delta_pct}`);
  }

  // 기존 임계값 검사 (변경 없음)
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
