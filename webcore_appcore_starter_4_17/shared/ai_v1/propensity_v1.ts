/**
 * AI Propensity Scoring v1 (IPS/SNIPS)
 * 
 * Meta-only input: treatment assignments, outcomes, propensity scores
 * Output: deterministic IPS/SNIPS estimates with over-intervention prevention
 */

export interface PropensityV1Input {
  samples: Array<{
    id: string;
    treatment: number; // 0 or 1
    outcome: number;
    propensity: number; // P(treatment | features)
  }>;
  method: "ips" | "snips";
}

export interface PropensityV1Output {
  estimate: number;
  variance: number;
  over_intervention_prevented: boolean;
  samples_used: number;
}

const MIN_PROPENSITY = 0.01; // Prevent extreme propensity scores
const MAX_PROPENSITY = 0.99;

export function propensityV1(input: PropensityV1Input): PropensityV1Output {
  // Deterministic: clip propensity scores to prevent over-intervention
  const clipped = input.samples.map(s => ({
    ...s,
    propensity: Math.max(MIN_PROPENSITY, Math.min(MAX_PROPENSITY, s.propensity)),
  }));
  
  let estimate = 0;
  let variance = 0;
  let total_weight = 0;
  
  for (const s of clipped) {
    const weight = input.method === "ips" 
      ? s.treatment / s.propensity
      : s.treatment / s.propensity; // SNIPS uses normalized weights
    
    estimate += weight * s.outcome;
    total_weight += weight;
  }
  
  if (input.method === "snips") {
    // SNIPS: normalize by sum of weights
    const normalization = clipped.reduce((sum, s) => sum + (s.treatment / s.propensity), 0);
    estimate = estimate / normalization;
  } else {
    // IPS: divide by sample count
    estimate = estimate / clipped.length;
  }
  
  // Calculate variance (simplified)
  for (const s of clipped) {
    const weight = s.treatment / s.propensity;
    const diff = (weight * s.outcome) - estimate;
    variance += diff * diff;
  }
  variance = variance / clipped.length;
  
  const over_intervention_prevented = clipped.every(s => 
    s.propensity >= MIN_PROPENSITY && s.propensity <= MAX_PROPENSITY
  );
  
  return {
    estimate: Math.round(estimate * 10000) / 10000,
    variance: Math.round(variance * 10000) / 10000,
    over_intervention_prevented,
    samples_used: clipped.length,
  };
}

