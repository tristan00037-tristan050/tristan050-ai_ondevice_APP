#!/usr/bin/env node
"use strict";

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const index = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
}

function computeVariance(values) {
  if (values.length === 0) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
  return variance;
}

function computeOutlierRatio(values, threshold) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const p95 = percentile(sorted, 95);
  const outliers = values.filter(v => v > threshold || v > p95 * 1.5).length;
  return outliers / values.length;
}

function verifyVarianceOutlier(input) {
  const {
    measurements = [],
    p50_variance_max = 100,
    p95_variance_max = 500,
    outlier_ratio_max = 0.05,
    outlier_threshold = null,
  } = input || {};

  if (!Array.isArray(measurements) || measurements.length === 0) {
    throw err("BLOCK: measurements array required and must not be empty", "MEASUREMENTS_REQUIRED");
  }

  // Compute percentiles
  const sorted = [...measurements].sort((a, b) => a - b);
  const p50 = percentile(sorted, 50);
  const p95 = percentile(sorted, 95);

  // Compute variance for p50 and p95 ranges
  const p50_range = measurements.filter(v => v <= p50 * 1.1 && v >= p50 * 0.9);
  const p95_range = measurements.filter(v => v <= p95 * 1.1 && v >= p95 * 0.9);

  const p50_var = computeVariance(p50_range);
  const p95_var = computeVariance(p95_range);

  // Variance check
  if (p50_var > p50_variance_max) {
    throw err(`BLOCK: p50 variance ${p50_var.toFixed(2)} exceeds max ${p50_variance_max}`, "P50_VARIANCE_EXCEEDED");
  }

  if (p95_var > p95_variance_max) {
    throw err(`BLOCK: p95 variance ${p95_var.toFixed(2)} exceeds max ${p95_variance_max}`, "P95_VARIANCE_EXCEEDED");
  }

  // Outlier ratio check
  const threshold = outlier_threshold !== null ? outlier_threshold : p95 * 1.5;
  const outlierRatio = computeOutlierRatio(measurements, threshold);

  if (outlierRatio > outlier_ratio_max) {
    throw err(`BLOCK: outlier ratio ${outlierRatio.toFixed(4)} exceeds max ${outlier_ratio_max}`, "OUTLIER_RATIO_EXCEEDED");
  }

  return {
    p50_variance: p50_var,
    p95_variance: p95_var,
    outlier_ratio: outlierRatio,
    passed: true,
  };
}

// Self-test mode
if (require.main === module) {
  try {
    // Test with sample data
    const testMeasurements = [10, 12, 11, 13, 10, 12, 11, 13, 10, 12, 15, 14, 12, 13, 11];
    const result = verifyVarianceOutlier({
      measurements: testMeasurements,
      p50_variance_max: 100,
      p95_variance_max: 500,
      outlier_ratio_max: 0.05,
    });

    console.log("AI_VARIANCE_OK=1");
    console.log("AI_OUTLIER_RATIO_OK=1");
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

module.exports = { verifyVarianceOutlier, computeVariance, computeOutlierRatio };

