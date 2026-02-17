#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function loadRegistry(registryPath) {
  const abs = path.isAbsolute(registryPath)
    ? registryPath
    : path.resolve(process.cwd(), registryPath);

  if (!fs.existsSync(abs)) throw err(`BLOCK: registry missing: ${abs}`, "REGISTRY_MISSING");

  const obj = JSON.parse(fs.readFileSync(abs, "utf8"));
  if (!obj || !Array.isArray(obj.reason_codes)) throw err("BLOCK: registry format invalid", "REGISTRY_FORMAT");

  return new Set(obj.reason_codes);
}

/**
 * reason_code가 registry에 등록되어 있는지 확인하고, 미등록이면 BLOCK.
 */
function gateReasonCodeV1(input) {
  const {
    reason_code,
    registry_path = "scripts/ops/reason_code_registry_v1.json",
  } = input || {};

  if (typeof reason_code !== "string" || reason_code.length === 0) {
    throw err("BLOCK: reason_code required", "REASON_CODE_REQUIRED");
  }

  const codes = loadRegistry(registry_path);

  if (!codes.has(reason_code)) {
    throw err(`BLOCK: reason_code not registered: ${reason_code}`, "REASON_CODE_NOT_REGISTERED");
  }

  return { allow: true, reason_code };
}

module.exports = { gateReasonCodeV1, loadRegistry };

