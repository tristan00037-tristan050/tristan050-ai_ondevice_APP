/**
 * Performance Downshift with Hysteresis
 * 
 * 다운시프트 레벨 계산 및 히스테리시스 적용 (채터링 방지)
 * 성능 예산 SSOT 유지, meta-only 기록
 */

import * as fs from 'fs';
import * as path from 'path';

interface PerformanceBudget {
  version: string;
  hysteresis: {
    upward_thresholds: Record<string, number>;
    downward_thresholds: Record<string, number>;
  };
  latency_buckets: Record<string, { min?: number; max?: number }>;
  budget_limits: {
    p95_latency_max_ms: number;
    fail_closed_on_exceed: boolean;
  };
}

interface DownshiftState {
  downshift_level: number;
  latency_bucket: string;
  hysteresis_state: 'STABLE' | 'UPWARD' | 'DOWNWARD';
}

let _budgetCache: PerformanceBudget | null = null;

/**
 * 성능 예산 SSOT 로드 (캐시 사용)
 */
function loadPerformanceBudget(): PerformanceBudget {
  if (_budgetCache) {
    return _budgetCache;
  }

  const budgetPath = path.join(
    __dirname,
    '../../../../config/step4b/performance_budget_v1.json'
  );

  try {
    const content = fs.readFileSync(budgetPath, 'utf-8');
    _budgetCache = JSON.parse(content) as PerformanceBudget;
    return _budgetCache;
  } catch (e) {
    // Fail-Closed: 예산 파일 없으면 기본값 사용 (최대 다운시프트)
    console.warn('[Performance Downshift] Failed to load budget, using defaults (Fail-Closed)');
    _budgetCache = {
      version: 'v1.0-fallback',
      hysteresis: {
        upward_thresholds: {
          L0_to_L1: 400,
          L1_to_L2: 600,
          L2_to_L3: 800,
          L3_to_L4: 1000,
        },
        downward_thresholds: {
          L4_to_L3: 700,
          L3_to_L2: 500,
          L2_to_L1: 300,
          L1_to_L0: 150,
        },
      },
      latency_buckets: {
        EXCELLENT: { max: 200 },
        GOOD: { min: 200, max: 400 },
        FAIR: { min: 400, max: 600 },
        POOR: { min: 600, max: 800 },
        VERY_POOR: { min: 800 },
      },
      budget_limits: {
        p95_latency_max_ms: 1000,
        fail_closed_on_exceed: true,
      },
    };
    return _budgetCache;
  }
}

/**
 * Latency를 버킷으로 분류 (meta-only)
 */
function bucketizeLatency(latencyMs: number): string {
  const budget = loadPerformanceBudget();
  const buckets = budget.latency_buckets;

  if (latencyMs < (buckets.EXCELLENT.max || 0)) {
    return 'EXCELLENT';
  }
  if (latencyMs >= (buckets.GOOD.min || 0) && latencyMs < (buckets.GOOD.max || 0)) {
    return 'GOOD';
  }
  if (latencyMs >= (buckets.FAIR.min || 0) && latencyMs < (buckets.FAIR.max || 0)) {
    return 'FAIR';
  }
  if (latencyMs >= (buckets.POOR.min || 0) && latencyMs < (buckets.POOR.max || 0)) {
    return 'POOR';
  }
  return 'VERY_POOR';
}

/**
 * 다운시프트 레벨 계산 (히스테리시스 적용)
 * 
 * @param latencyMs 현재 P95 latency (ms)
 * @param currentLevel 현재 downshift_level (0-4)
 * @returns 다운시프트 상태 (meta-only)
 */
export function calculateDownshift(
  latencyMs: number,
  currentLevel: number = 0
): DownshiftState {
  const budget = loadPerformanceBudget();
  const hysteresis = budget.hysteresis;

  // 예산 상한 검사 (Fail-Closed)
  if (latencyMs > budget.budget_limits.p95_latency_max_ms) {
    // 예산 상한 초과: 최대 다운시프트 (레벨 4)
    return {
      downshift_level: 4,
      latency_bucket: bucketizeLatency(latencyMs),
      hysteresis_state: 'UPWARD',
    };
  }

  // 히스테리시스 적용: 상향/하향 임계치 분리
  let newLevel = currentLevel;
  let state: 'STABLE' | 'UPWARD' | 'DOWNWARD' = 'STABLE';

  // 상향 임계치 체크 (downshift_level 증가)
  if (currentLevel === 0 && latencyMs >= hysteresis.upward_thresholds.L0_to_L1) {
    newLevel = 1;
    state = 'UPWARD';
  } else if (currentLevel === 1 && latencyMs >= hysteresis.upward_thresholds.L1_to_L2) {
    newLevel = 2;
    state = 'UPWARD';
  } else if (currentLevel === 2 && latencyMs >= hysteresis.upward_thresholds.L2_to_L3) {
    newLevel = 3;
    state = 'UPWARD';
  } else if (currentLevel === 3 && latencyMs >= hysteresis.upward_thresholds.L3_to_L4) {
    newLevel = 4;
    state = 'UPWARD';
  }
  // 하향 임계치 체크 (downshift_level 감소)
  else if (currentLevel === 4 && latencyMs <= hysteresis.downward_thresholds.L4_to_L3) {
    newLevel = 3;
    state = 'DOWNWARD';
  } else if (currentLevel === 3 && latencyMs <= hysteresis.downward_thresholds.L3_to_L2) {
    newLevel = 2;
    state = 'DOWNWARD';
  } else if (currentLevel === 2 && latencyMs <= hysteresis.downward_thresholds.L2_to_L1) {
    newLevel = 1;
    state = 'DOWNWARD';
  } else if (currentLevel === 1 && latencyMs <= hysteresis.downward_thresholds.L1_to_L0) {
    newLevel = 0;
    state = 'DOWNWARD';
  } else {
    // 히스테리시스 범위 내: 레벨 유지
    state = 'STABLE';
  }

  return {
    downshift_level: newLevel,
    latency_bucket: bucketizeLatency(latencyMs),
    hysteresis_state: state,
  };
}

/**
 * 다운시프트 상태를 meta-only 형식으로 기록
 * (원문/본문 로그 금지)
 */
export function logDownshiftState(state: DownshiftState): void {
  // Meta-only: 숫자/버킷/상태만 기록
  console.log('[Performance Downshift]', {
    downshift_level: state.downshift_level,
    latency_bucket: state.latency_bucket,
    hysteresis_state: state.hysteresis_state,
  });
}

