#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function sha256Hex(s) {
  return crypto.createHash("sha256").update(String(s), "utf8").digest("hex");
}

function canonicalizeInput(input) {
  // Canonical JSON representation for deterministic hashing
  return JSON.stringify(input, Object.keys(input).sort());
}

function computeFingerprint(input, seed) {
  const canonical = canonicalizeInput(input);
  const combined = `${canonical}:${seed}`;
  return sha256Hex(combined);
}

function loadGoldenVectors(ssotPath) {
  const abs = path.isAbsolute(ssotPath)
    ? ssotPath
    : path.resolve(process.cwd(), ssotPath);

  if (!fs.existsSync(abs)) throw err(`BLOCK: SSOT missing: ${abs}`, "SSOT_MISSING");

  const obj = JSON.parse(fs.readFileSync(abs, "utf8"));
  if (!obj || !Array.isArray(obj.vectors)) throw err("BLOCK: invalid SSOT format", "SSOT_FORMAT");

  return obj.vectors;
}

function verifyDeterminism(vectors) {
  const failures = [];

  // Allowed modes (SSOT-aligned)
  const ALLOWED_MODES = new Set(["deterministic", "prod", "mock", "shadow"]);

  for (const vec of vectors) {
    if (!vec.test_id || !vec.input || typeof vec.seed !== "number" || !vec.expected_fingerprint) {
      failures.push(`BLOCK: invalid vector format: ${vec.test_id || "unknown"}`);
      continue;
    }

    // Mode validation (required)
    if (typeof vec.mode !== "string" || vec.mode.trim().length === 0) {
      failures.push(`BLOCK: vec.mode is required for ${vec.test_id || "unknown"}`);
      continue;
    }

    // Mode allowlist validation
    if (!ALLOWED_MODES.has(vec.mode)) {
      failures.push(`BLOCK: vec.mode invalid: ${vec.mode} for ${vec.test_id || "unknown"}`);
      continue;
    }

    // Compute fingerprint from input
    const computed = computeFingerprint(vec.input, vec.seed);

    // Verify determinism: same input + seed = same fingerprint
    if (computed !== vec.expected_fingerprint) {
      failures.push(`BLOCK: fingerprint mismatch for ${vec.test_id}: expected ${vec.expected_fingerprint}, got ${computed}`);
    }
  }

  if (failures.length > 0) {
    throw err(failures.join("\n"), "DETERMINISM_FAILED");
  }
}

function main() {
  const ssotPath = process.argv[2] || "scripts/ai/golden_vectors_v2.json";

  try {
    const vectors = loadGoldenVectors(ssotPath);
    verifyDeterminism(vectors);
    console.log("AI_GOLDEN_VECTORS_V2_OK=1");
    console.log("AI_DETERMINISM_FINGERPRINT_OK=1");
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

main();

