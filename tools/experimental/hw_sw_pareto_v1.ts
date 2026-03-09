'use strict';

// P24-R-03: HW_SW_CODESIGN_PARETO_V1
// 실험 레인 — production 라우팅에 미연결

export interface ParetoPoint {
  strategy_id: string;
  soc_family: string;
  accuracy_score: number;       // 0.0~1.0
  latency_p95_ms: number;
  memory_mb: number;
  thermal_risk: number;         // 0.0~1.0
  is_pareto_optimal: boolean;
}

export function computeParetoFrontier(points: ParetoPoint[]): ParetoPoint[] {
  // accuracy 최대화, latency/memory/thermal 최소화
  // 다른 모든 점에 의해 지배되지 않는 점이 Pareto optimal
  return points.map(p => {
    const dominated = points.some(
      other =>
        other.strategy_id !== p.strategy_id &&
        other.accuracy_score >= p.accuracy_score &&
        other.latency_p95_ms <= p.latency_p95_ms &&
        other.memory_mb <= p.memory_mb &&
        other.thermal_risk <= p.thermal_risk &&
        (
          other.accuracy_score > p.accuracy_score ||
          other.latency_p95_ms < p.latency_p95_ms ||
          other.memory_mb < p.memory_mb ||
          other.thermal_risk < p.thermal_risk
        ),
    );
    return { ...p, is_pareto_optimal: !dominated };
  });
}

export function getParetoOptimal(points: ParetoPoint[]): ParetoPoint[] {
  return computeParetoFrontier(points).filter(p => p.is_pareto_optimal);
}
