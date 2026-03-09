'use strict';

/**
 * Heavy Hitter Oracle (H2O) KV Cache
 * 실험 레인 — production 라우팅에 미연결
 * @experimental
 */

// P24-R-01: H2O_KV_EXPERIMENTAL_V1

export interface H2OConfig {
  max_cache_tokens: number;
  heavy_hitter_ratio: number;   // 0.0~1.0, 보통 0.2~0.4
  recent_window_size: number;
}

export interface H2OCacheState {
  heavy_hitter_token_ids: number[];
  recent_token_ids: number[];
  attention_score_accumulator: Map<number, number>;
  config: H2OConfig;
}

export function createH2OCache(config: H2OConfig): H2OCacheState {
  if (config.heavy_hitter_ratio < 0 || config.heavy_hitter_ratio > 1) {
    throw new RangeError('H2O_INVALID_HEAVY_HITTER_RATIO');
  }
  return {
    heavy_hitter_token_ids: [],
    recent_token_ids: [],
    attention_score_accumulator: new Map(),
    config,
  };
}

export function updateH2OCache(
  state: H2OCacheState,
  new_token_id: number,
  attention_score: number,
): H2OCacheState {
  // 1. attention score 누적
  const prev = state.attention_score_accumulator.get(new_token_id) ?? 0;
  const newAccumulator = new Map(state.attention_score_accumulator);
  newAccumulator.set(new_token_id, prev + attention_score);

  // 2. recent window 업데이트
  const newRecent = [...state.recent_token_ids, new_token_id].slice(
    -state.config.recent_window_size,
  );

  // 3. heavy hitter 재선정 (상위 heavy_hitter_ratio 비율)
  const sorted = [...newAccumulator.entries()]
    .sort((a, b) => b[1] - a[1]);
  const hh_count = Math.max(
    1,
    Math.floor(state.config.max_cache_tokens * state.config.heavy_hitter_ratio),
  );
  const newHeavyHitters = sorted.slice(0, hh_count).map(([id]) => id);

  return {
    ...state,
    heavy_hitter_token_ids: newHeavyHitters,
    recent_token_ids: newRecent,
    attention_score_accumulator: newAccumulator,
    config: state.config,
  };
}

export function getEffectiveCacheTokenIds(state: H2OCacheState): number[] {
  const combined = new Set([
    ...state.heavy_hitter_token_ids,
    ...state.recent_token_ids,
  ]);
  return [...combined].slice(0, state.config.max_cache_tokens);
}

export function getH2OStats(state: H2OCacheState): {
  heavy_hitter_count: number;
  recent_count: number;
  effective_cache_size: number;
  estimated_memory_reduction_pct: number;
} {
  const effective = getEffectiveCacheTokenIds(state).length;
  return {
    heavy_hitter_count: state.heavy_hitter_token_ids.length,
    recent_count: state.recent_token_ids.length,
    effective_cache_size: effective,
    estimated_memory_reduction_pct:
      Math.round((1 - effective / state.config.max_cache_tokens) * 100),
  };
}
