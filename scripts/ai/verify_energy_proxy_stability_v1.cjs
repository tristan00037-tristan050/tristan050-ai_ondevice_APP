#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { computeEnergyProxyV1 } = require("./energy_proxy_v1.cjs");

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

function loadMeasurementsFromFile(filePath) {
  const abs = path.isAbsolute(filePath)
    ? filePath
    : path.resolve(process.cwd(), filePath);

  if (!fs.existsSync(abs)) {
    throw err(`BLOCK: measurements file missing: ${abs}`, "MEASUREMENTS_FILE_MISSING");
  }

  let obj;
  try {
    const content = fs.readFileSync(abs, "utf8");
    obj = JSON.parse(content);
  } catch (e) {
    throw err(`BLOCK: failed to parse measurements file: ${e.message}`, "MEASUREMENTS_PARSE_FAILED");
  }

  if (!obj || !Array.isArray(obj.samples)) {
    throw err("BLOCK: measurements file must contain 'samples' array", "MEASUREMENTS_FORMAT_INVALID");
  }

  return obj.samples;
}

function verifyEnergyProxyStability(input) {
  const {
    samples = [],
    relative_tolerance = 0.05,
    absolute_tolerance = 1.0,
    p95_p50_ratio_max = 2.0,
  } = input || {};

  if (!Array.isArray(samples) || samples.length === 0) {
    throw err("BLOCK: samples array required and must not be empty", "SAMPLES_REQUIRED");
  }

  const computed = [];
  const errors = [];

  // Compute energy proxy for each sample
  for (let i = 0; i < samples.length; i++) {
    const sample = samples[i];
    try {
      const energy = computeEnergyProxyV1(sample);
      computed.push(energy);

      // Compare with expected if provided
      if (typeof sample.expected_energy_proxy === "number") {
        const diff = Math.abs(energy - sample.expected_energy_proxy);
        const relError = diff / Math.max(Math.abs(sample.expected_energy_proxy), 1e-10);

        if (diff > absolute_tolerance && relError > relative_tolerance) {
          errors.push(`BLOCK: sample ${i} energy proxy ${energy.toFixed(2)} differs from expected ${sample.expected_energy_proxy.toFixed(2)} (diff=${diff.toFixed(2)}, rel=${relError.toFixed(4)})`);
        }
      }
    } catch (e) {
      errors.push(`BLOCK: sample ${i} computation failed: ${e.message}`);
    }
  }

  if (errors.length > 0) {
    throw err(errors.join("\n"), "STABILITY_FAILED");
  }

  // Variance/outlier check: p95/p50 ratio
  if (computed.length > 0) {
    const sorted = [...computed].sort((a, b) => a - b);
    const p50 = percentile(sorted, 50);
    const p95 = percentile(sorted, 95);

    if (p50 > 0) {
      const ratio = p95 / p50;
      if (ratio > p95_p50_ratio_max) {
        throw err(`BLOCK: p95/p50 ratio ${ratio.toFixed(2)} exceeds max ${p95_p50_ratio_max}`, "VARIANCE_EXCEEDED");
      }
    }
  }

  return {
    computed_count: computed.length,
    passed: true,
  };
}

// CLI mode
if (require.main === module) {
  try {
    // Parse CLI arguments
    const args = process.argv.slice(2);
    let measurementsJsonPath = null;

    for (let i = 0; i < args.length; i++) {
      if (args[i] === "--measurements_json" && i + 1 < args.length) {
        measurementsJsonPath = args[i + 1];
        break;
      }
    }

    if (!measurementsJsonPath) {
      throw err("BLOCK: --measurements_json <path> required", "MEASUREMENTS_JSON_REQUIRED");
    }

    // Load measurements from file
    const samples = loadMeasurementsFromFile(measurementsJsonPath);

    // Verify stability
    const result = verifyEnergyProxyStability({
      samples,
      relative_tolerance: 0.05,
      absolute_tolerance: 1.0,
      p95_p50_ratio_max: 2.0,
    });

    console.log("AI_ENERGY_PROXY_DEFINITION_SSOT_OK=1");
    console.log("AI_ENERGY_MEASUREMENTS_SOURCE_OK=1");
    console.log("AI_ENERGY_STABILITY_OK=1");
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

module.exports = { verifyEnergyProxyStability, loadMeasurementsFromFile };

