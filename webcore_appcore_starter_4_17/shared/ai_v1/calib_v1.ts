/**
 * AI Calibration v1
 * 
 * Meta-only input: predicted probabilities, observed outcomes
 * Output: deterministic calibration metrics with over-intervention prevention
 */

export interface CalibV1Input {
  predictions: Array<{ id: string; prob: number }>;
  observed: Array<{ id: string; outcome: number }>;
  intervention_threshold: number;
}

export interface CalibV1Output {
  calibration_error: number;
  over_intervention_prevented: boolean;
  interventions_blocked: number;
}

const MAX_INTERVENTION_RATE = 0.1; // 10% max intervention rate

export function calibV1(input: CalibV1Input): CalibV1Output {
  // Deterministic: calculate calibration error
  let total_error = 0;
  let interventions = 0;
  let interventions_blocked = 0;
  
  for (const pred of input.predictions) {
    const obs = input.observed.find(o => o.id === pred.id);
    if (!obs) continue;
    
    const error = Math.abs(pred.prob - obs.outcome);
    total_error += error;
    
    // Over-intervention prevention: block if intervention rate would exceed threshold
    if (pred.prob >= input.intervention_threshold) {
      interventions++;
      const current_rate = interventions / input.predictions.length;
      if (current_rate > MAX_INTERVENTION_RATE) {
        interventions_blocked++;
      }
    }
  }
  
  const calibration_error = total_error / input.predictions.length;
  const over_intervention_prevented = (interventions - interventions_blocked) / input.predictions.length <= MAX_INTERVENTION_RATE;
  
  return {
    calibration_error: Math.round(calibration_error * 10000) / 10000,
    over_intervention_prevented,
    interventions_blocked,
  };
}

