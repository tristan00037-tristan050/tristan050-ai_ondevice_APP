#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const crypto = require("crypto");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function validateApprovalFormat(approval) {
  if (!approval || typeof approval !== "object") {
    throw err("BLOCK: approval must be an object", "APPROVAL_FORMAT");
  }

  const required = ["approval_token_sha256", "approval_scope", "approved_at_utc"];
  for (const key of required) {
    if (!approval[key] || typeof approval[key] !== "string") {
      throw err(`BLOCK: approval missing or invalid ${key}`, "APPROVAL_FORMAT");
    }
  }

  // Validate SHA256 format (64 hex chars)
  if (!/^[0-9a-f]{64}$/i.test(approval.approval_token_sha256)) {
    throw err("BLOCK: approval_token_sha256 must be 64 hex chars", "APPROVAL_FORMAT");
  }

  // Validate ISO 8601 timestamp
  const ts = new Date(approval.approved_at_utc);
  if (isNaN(ts.getTime())) {
    throw err("BLOCK: approved_at_utc must be valid ISO 8601", "APPROVAL_FORMAT");
  }

  return true;
}

function hashScope(scope) {
  if (!scope || typeof scope !== "string") {
    throw err("BLOCK: scope must be a non-empty string", "SCOPE");
  }
  return crypto.createHash("sha256").update(scope).digest("hex");
}

function checkHighRiskGate(riskLevel, reasonCode, scopeHash, approval, taintState) {
  const risk = String(riskLevel || "").toUpperCase();
  const taint = taintState === 1 || taintState === true;

  // LOW/OK: always allow, no taint
  if (risk === "LOW" || risk === "OK") {
    return { allow: true, taint: 0, reason: "LOW_RISK" };
  }

  // HIGH risk: requires approval
  if (risk === "HIGH") {
    if (!approval) {
      throw err("BLOCK: HIGH risk requires approval", "HIGH_RISK_NO_APPROVAL");
    }

    // Validate approval format
    validateApprovalFormat(approval);

    // Verify scope match
    const expectedScope = scopeHash || hashScope(reasonCode || "");
    if (approval.approval_scope !== expectedScope) {
      throw err("BLOCK: approval scope mismatch", "APPROVAL_SCOPE_MISMATCH");
    }

    // HIGH with approval → ALLOW + taint=1
    return { allow: true, taint: 1, reason: "HIGH_RISK_APPROVED" };
  }

  // Unknown risk level
  throw err(`BLOCK: unknown risk_level=${risk}`, "UNKNOWN_RISK");
}

function checkTaintPropagation(taintState, approval) {
  const taint = taintState === 1 || taintState === true;

  // If tainted, require approval to proceed
  if (taint) {
    if (!approval) {
      throw err("BLOCK: taint propagation requires approval", "TAINT_NO_APPROVAL");
    }

    // Validate approval format
    validateApprovalFormat(approval);

    return { allow: true, taint: 1, reason: "TAINT_APPROVED" };
  }

  // No taint: allow
  return { allow: true, taint: 0, reason: "NO_TAINT" };
}

function gateHighRiskV1(input) {
  const {
    risk_level,
    reason_code,
    scope_hash,
    approval_token,
    taint_state = 0,
  } = input || {};

  // First check taint propagation (if tainted, approval required)
  if (taint_state === 1 || taint_state === true) {
    return checkTaintPropagation(taint_state, approval_token);
  }

  // Then check risk level gate
  return checkHighRiskGate(risk_level, reason_code, scope_hash, approval_token, taint_state);
}

module.exports = {
  gateHighRiskV1,
  validateApprovalFormat,
  hashScope,
};

