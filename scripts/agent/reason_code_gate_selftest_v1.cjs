#!/usr/bin/env node
"use strict";

const { gateReasonCodeV1 } = require("./reason_code_gate_v1.cjs");

function ok(name) { console.log(`${name}=1`); }
function fail(name, msg) { console.error(`FAIL:${name}:${msg}`); process.exit(1); }

function mustThrow(name, fn, codePrefix) {
  let threw = false;
  try { fn(); }
  catch (e) {
    threw = true;
    if (codePrefix && !String(e.code || "").startsWith(codePrefix)) {
      fail(name, `unexpected code=${e.code}`);
    }
  }
  if (!threw) fail(name, "expected throw but succeeded");
}

// 1) 등록된 코드는 통과
try {
  const result = gateReasonCodeV1({ reason_code: "OK" });
  if (!result.allow || result.reason_code !== "OK") {
    fail("REASON_CODE_REGISTRY_PRESENT_OK", "registered code failed");
  }
} catch (e) {
  fail("REASON_CODE_REGISTRY_PRESENT_OK", e.message);
}

// 2) 미등록 코드는 BLOCK
mustThrow("REASON_CODE_NOT_REGISTERED_BLOCK_OK", () => {
  gateReasonCodeV1({ reason_code: "NOT_IN_REGISTRY" });
}, "REASON_CODE_NOT_REGISTERED");

// 3) 단일 소스 확인 (registry 파일 존재 및 형식 검증)
try {
  const { loadRegistry } = require("./reason_code_gate_v1.cjs");
  const codes = loadRegistry("scripts/ops/reason_code_registry_v1.json");
  if (!codes || codes.size === 0) {
    fail("REASON_CODE_SINGLE_SOURCE_OK", "registry empty or invalid");
  }
  // 등록된 코드가 실제로 작동하는지 확인
  if (!codes.has("OK")) {
    fail("REASON_CODE_SINGLE_SOURCE_OK", "expected code 'OK' not in registry");
  }
} catch (e) {
  fail("REASON_CODE_SINGLE_SOURCE_OK", e.message);
}

ok("REASON_CODE_REGISTRY_PRESENT_OK");
ok("REASON_CODE_NOT_REGISTERED_BLOCK_OK");
ok("REASON_CODE_SINGLE_SOURCE_OK");
process.exit(0);

