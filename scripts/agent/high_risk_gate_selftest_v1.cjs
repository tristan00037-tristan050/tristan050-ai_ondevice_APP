#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const crypto = require("crypto");
const { gateHighRiskV1, validateApprovalFormat, hashScope } = require("./high_risk_gate_v1.cjs");

function ok(name) {
  console.log(`${name}=1`);
}
function fail(name, msg) {
  console.error(`FAIL:${name}:${msg}`);
  process.exit(1);
}
function mustThrow(name, fn, codePrefix) {
  let threw = false;
  try {
    fn();
  } catch (e) {
    threw = true;
    if (codePrefix && !String(e.code || "").startsWith(codePrefix)) {
      fail(name, `unexpected code=${e.code}`);
    }
  }
  if (!threw) fail(name, "expected throw but succeeded");
}
function mustAllow(name, fn, expectTaint) {
  try {
    const result = fn();
    if (!result.allow) {
      fail(name, "expected allow=true");
    }
    const taint = result.taint === 1 || result.taint === true;
    if (expectTaint && !taint) {
      fail(name, "expected taint=1");
    }
    if (!expectTaint && taint) {
      fail(name, "expected taint=0");
    }
  } catch (e) {
    fail(name, `unexpected error: ${e.message}`);
  }
}

// Test 1: HIGH + 승인 없음 → BLOCK
mustThrow("HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK", () => {
  gateHighRiskV1({
    risk_level: "HIGH",
    reason_code: "test_scope",
    scope_hash: hashScope("test_scope"),
  });
}, "HIGH_RISK_NO_APPROVAL");

// Test 2: HIGH + 승인 있음 → ALLOW + taint=1
const approvalToken = "test_approval_token_12345";
const approvalTokenSha256 = crypto.createHash("sha256").update(approvalToken).digest("hex");
const testScope = "test_scope";
const testScopeHash = hashScope(testScope);
const validApproval = {
  approval_token_sha256: approvalTokenSha256,
  approval_scope: testScopeHash,
  approved_at_utc: new Date().toISOString(),
};

mustAllow("HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK", () => {
  return gateHighRiskV1({
    risk_level: "HIGH",
    reason_code: testScope,
    scope_hash: testScopeHash,
    approval_token: validApproval,
  });
}, true); // expect taint=1

// Test 3: taint=1 상태에서 승인 없음 → BLOCK (전파 검증)
mustThrow("HIGH_RISK_TAINT_PROPAGATION_OK", () => {
  gateHighRiskV1({
    risk_level: "LOW", // even LOW risk
    taint_state: 1, // but tainted
  });
}, "TAINT_NO_APPROVAL");

// Test 4: taint=1 + 승인 있음 → ALLOW + taint=1 (전파)
mustAllow("HIGH_RISK_TAINT_PROPAGATION_OK", () => {
  return gateHighRiskV1({
    risk_level: "LOW",
    taint_state: 1,
    approval_token: validApproval,
  });
}, true); // expect taint=1

// Test 5: LOW/OK는 taint 없이 통과
mustAllow("HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK", () => {
  return gateHighRiskV1({
    risk_level: "LOW",
    reason_code: "test",
  });
}, false); // expect taint=0

mustAllow("HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK", () => {
  return gateHighRiskV1({
    risk_level: "OK",
    reason_code: "test",
  });
}, false); // expect taint=0

// Test 6: Approval format validation
mustThrow("HIGH_RISK_APPROVAL_FORMAT_OK", () => {
  validateApprovalFormat(null);
}, "APPROVAL_FORMAT");

mustThrow("HIGH_RISK_APPROVAL_FORMAT_OK", () => {
  validateApprovalFormat({});
}, "APPROVAL_FORMAT");

mustThrow("HIGH_RISK_APPROVAL_FORMAT_OK", () => {
  validateApprovalFormat({
    approval_token_sha256: "invalid",
    approval_scope: "test",
    approved_at_utc: "invalid",
  });
}, "APPROVAL_FORMAT");

// Valid format should not throw
try {
  validateApprovalFormat(validApproval);
} catch (e) {
  fail("HIGH_RISK_APPROVAL_FORMAT_OK", `valid approval rejected: ${e.message}`);
}

// Test A (P2 봉인): taint_state: "1" 승인 없음 → BLOCK
mustThrow("HIGH_RISK_TAINT_STRING_BLOCK_OK", () => {
  gateHighRiskV1({ risk_level: "LOW", taint_state: "1" });
}, "TAINT_NO_APPROVAL");

// Test B (P1 봉인): taint=1 + HIGH + 승인 있으나 scope mismatch → BLOCK
const wrongApproval = {
  ...validApproval,
  approval_scope: hashScope("different_scope"),
};
mustThrow("HIGH_RISK_TAINT_HIGH_SCOPE_ENFORCED_OK", () => {
  gateHighRiskV1({
    risk_level: "HIGH",
    reason_code: testScope,
    scope_hash: testScopeHash,
    taint_state: 1,
    approval_token: wrongApproval,
  });
}, "APPROVAL_SCOPE_MISMATCH");

ok("HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK");
ok("HIGH_RISK_TAINT_PROPAGATION_OK");
ok("HIGH_RISK_APPROVAL_FORMAT_OK");
ok("HIGH_RISK_TAINT_STRING_BLOCK_OK");
ok("HIGH_RISK_TAINT_HIGH_SCOPE_ENFORCED_OK");
process.exit(0);

