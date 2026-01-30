/**
 * AI Rerank with NearTie v1
 * 
 * Meta-only input: ranking scores, tie thresholds
 * Output: deterministic reranked list with NearTie swap budget enforcement
 */

export interface RerankNearTieV1Input {
  items: Array<{ id: string; score: number }>;
  tie_threshold: number;
  max_swaps: number;
}

export interface RerankNearTieV1Output {
  reranked: Array<{ id: string; score: number; original_rank: number }>;
  swaps_used: number;
  swap_budget_ok: boolean;
}

const MAX_SWAP_BUDGET = 3; // Maximum swaps allowed

export function rerankNearTieV1(input: RerankNearTieV1Input): RerankNearTieV1Output {
  // Deterministic: stable sort by score (descending)
  const sorted = [...input.items]
    .map((item, idx) => ({ ...item, original_rank: idx }))
    .sort((a, b) => {
      // If scores are within tie_threshold, consider them tied (stable order)
      if (Math.abs(a.score - b.score) <= input.tie_threshold) {
        return a.id.localeCompare(b.id); // Deterministic tie-breaker
      }
      return b.score - a.score;
    });
  
  // Count swaps (items that moved from original position)
  let swaps = 0;
  const reranked = sorted.map((item, newRank) => {
    if (item.original_rank !== newRank) {
      swaps++;
    }
    return { id: item.id, score: item.score, original_rank: item.original_rank };
  });
  
  const swap_budget_ok = swaps <= MAX_SWAP_BUDGET;
  
  return {
    reranked,
    swaps_used: swaps,
    swap_budget_ok,
  };
}

