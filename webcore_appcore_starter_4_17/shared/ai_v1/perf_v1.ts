/**
 * AI Performance Harness v1
 * 
 * Meta-only input: performance metrics (latency_ms, throughput, etc.)
 * Output: deterministic performance score with P95 budget enforcement
 */

export interface PerfV1Input {
  latency_ms: number;
  throughput: number;
  error_rate: number;
  ts_utc: string;
}

export interface PerfV1Output {
  score: number;
  p95_budget_ok: boolean;
  budget_exceeded_ms?: number;
}

const P95_BUDGET_MS = 100; // 100ms P95 budget

export function perfV1(input: PerfV1Input): PerfV1Output {
  // Deterministic: same input always produces same output
  const score = Math.max(0, 100 - (input.latency_ms * 0.5) - (input.error_rate * 100));
  const p95_budget_ok = input.latency_ms <= P95_BUDGET_MS;
  const budget_exceeded_ms = p95_budget_ok ? undefined : input.latency_ms - P95_BUDGET_MS;
  
  return {
    score: Math.round(score * 100) / 100,
    p95_budget_ok,
    budget_exceeded_ms,
  };
}

