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

function loadRegistry(registryPath) {
  const abs = path.isAbsolute(registryPath)
    ? registryPath
    : path.resolve(process.cwd(), registryPath);

  if (!fs.existsSync(abs)) throw err(`BLOCK: registry missing: ${abs}`, "REGISTRY_MISSING");

  const obj = JSON.parse(fs.readFileSync(abs, "utf8"));
  if (!obj || !Array.isArray(obj.layers)) throw err("BLOCK: registry format invalid", "REGISTRY_FORMAT");

  return new Set(obj.layers);
}

/**
 * input.raw_text는 해시 계산에만 사용하고, 반환/저장 객체에 포함하지 않는다.
 */
function recordInstructionLayerV1(input) {
  const {
    layer_id,
    scope,
    reason_code,
    raw_text,
    registry_path = "scripts/agent/instruction_layers_registry_v1.json",
  } = input || {};

  const layers = loadRegistry(registry_path);

  if (!layers.has(layer_id)) {
    throw err(`BLOCK: layer_id not registered: ${layer_id}`, "LAYER_NOT_REGISTERED");
  }

  if (typeof raw_text !== "string" || raw_text.length === 0) {
    throw err("BLOCK: raw_text required for hashing", "RAW_REQUIRED");
  }

  // meta-only output (원문 0)
  const out = {
    layer_id,
    scope_hash: sha256Hex(scope || ""),
    reason_code: String(reason_code || "UNSPECIFIED"),
    raw_sha256: sha256Hex(raw_text),
    raw_len: raw_text.length,
    ts_utc: new Date().toISOString(),
  };

  return out;
}

module.exports = { recordInstructionLayerV1, loadRegistry, sha256Hex };

