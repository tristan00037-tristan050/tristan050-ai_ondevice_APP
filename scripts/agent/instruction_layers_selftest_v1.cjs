#!/usr/bin/env node
"use strict";

const { recordInstructionLayerV1 } = require("./instruction_layers_v1.cjs");

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

const SECRET = "SENSITIVE_TOKEN_ABC_123";

// 1) registry enforcement
mustThrow("INSTRUCTION_LAYER_REGISTRY_OK", () => {
  recordInstructionLayerV1({
    layer_id: "not_registered",
    scope: "scopeA",
    reason_code: "TEST",
    raw_text: SECRET,
  });
}, "LAYER_NOT_REGISTERED");

// 2) meta-only output: must not include raw text
let out;
try {
  out = recordInstructionLayerV1({
    layer_id: "task",
    scope: "scopeA",
    reason_code: "TEST",
    raw_text: SECRET,
  });
} catch (e) {
  fail("INSTRUCTION_HASH_ONLY_OK", e.message);
}

const outStr = JSON.stringify(out);
if (outStr.includes(SECRET)) fail("INSTRUCTION_RAW_0_OK", "raw text leaked in output");
if (!out.raw_sha256 || out.raw_sha256.length < 32) fail("INSTRUCTION_HASH_ONLY_OK", "missing raw_sha256");
if (!out.scope_hash || out.scope_hash.length < 32) fail("INSTRUCTION_HASH_ONLY_OK", "missing scope_hash");

ok("INSTRUCTION_LAYER_REGISTRY_OK");
ok("INSTRUCTION_HASH_ONLY_OK");
ok("INSTRUCTION_RAW_0_OK");
process.exit(0);

