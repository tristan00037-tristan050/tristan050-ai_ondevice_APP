#!/usr/bin/env node
"use strict";

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

/**
 * Compute energy proxy from sample inputs.
 * Formula: (latency_ms * 0.5) + (mem_mb * 0.1) + (steps * 0.2) + device_factor
 * device_factor: cpu=0, gpu=-0.5
 */
function computeEnergyProxyV1(sample) {
  if (!sample || typeof sample !== "object") {
    throw err("BLOCK: sample must be an object", "SAMPLE_INVALID");
  }

  const { latency_ms, mem_mb, steps, device_class } = sample;

  // Input validation
  if (typeof latency_ms !== "number" || latency_ms < 0 || !Number.isFinite(latency_ms)) {
    throw err("BLOCK: latency_ms must be a non-negative finite number", "LATENCY_INVALID");
  }

  if (typeof mem_mb !== "number" || mem_mb < 0 || !Number.isFinite(mem_mb)) {
    throw err("BLOCK: mem_mb must be a non-negative finite number", "MEM_INVALID");
  }

  if (typeof steps !== "number" || steps < 0 || !Number.isFinite(steps)) {
    throw err("BLOCK: steps must be a non-negative finite number", "STEPS_INVALID");
  }

  if (typeof device_class !== "string" || !device_class.trim()) {
    throw err("BLOCK: device_class must be a non-empty string", "DEVICE_CLASS_INVALID");
  }

  // Device factor
  const device_factor = device_class.toLowerCase() === "gpu" ? -0.5 : 0;

  // Energy proxy formula
  const energy_proxy = (latency_ms * 0.5) + (mem_mb * 0.1) + (steps * 0.2) + device_factor;

  return energy_proxy;
}

module.exports = { computeEnergyProxyV1 };

