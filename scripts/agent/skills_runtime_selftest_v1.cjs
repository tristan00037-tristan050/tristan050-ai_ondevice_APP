#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const path = require("path");
const { gateSkillsRuntimeV1 } = require("./skills_runtime_gate_v1.cjs");

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

function mustAllow(name, fn, expectProof) {
  try {
    const result = fn();
    if (!result.allow) {
      fail(name, "expected allow=true");
    }
    if (expectProof) {
      if (!result.proof || typeof result.proof !== "object") {
        fail(name, "expected proof object");
      }
      if (result.proof.meta_only_proof !== true) {
        fail(name, "expected meta_only_proof=true");
      }
      // 원문 0 검증: proof에 raw data가 없어야 함
      const proofStr = JSON.stringify(result.proof);
      if (proofStr.includes("raw") || proofStr.includes("data") || proofStr.includes("content")) {
        fail(name, "proof must not contain raw data (meta-only)");
      }
    }
  } catch (e) {
    fail(name, `unexpected error: ${e.message}`);
  }
}

const manifestPath = path.join(__dirname, "skills_manifest_v1.json");

// Test 1: 미등록 skill_id → BLOCK
mustThrow("SKILLS_CAPABILITY_GATE_BLOCK_OK", () => {
  gateSkillsRuntimeV1({
    skill_id: "unknown.skill",
    requested_capabilities: ["read_only"],
    manifest_path: manifestPath,
  });
}, "SKILL_NOT_REGISTERED");

// Test 2: 등록 skill이지만 capability 초과 요청 → BLOCK
mustThrow("SKILLS_CAPABILITY_GATE_BLOCK_OK", () => {
  gateSkillsRuntimeV1({
    skill_id: "example.echo",
    requested_capabilities: ["read_only", "write"], // write는 manifest에 없음
    manifest_path: manifestPath,
  });
}, "CAPABILITY_NOT_ALLOWED");

// Test 3: 정상 요청 → ALLOW + meta-only proof 생성
mustAllow("SKILLS_META_ONLY_PROOF_OK", () => {
  return gateSkillsRuntimeV1({
    skill_id: "example.echo",
    requested_capabilities: ["read_only"],
    manifest_path: manifestPath,
  });
}, true); // expect proof

// Test 4: 빈 capabilities 배열도 허용 (subset of manifest)
mustAllow("SKILLS_META_ONLY_PROOF_OK", () => {
  return gateSkillsRuntimeV1({
    skill_id: "example.echo",
    requested_capabilities: [],
    manifest_path: manifestPath,
  });
}, true);

// Test 5: manifest 파일이 없으면 BLOCK
mustThrow("SKILLS_MANIFEST_PRESENT_OK", () => {
  gateSkillsRuntimeV1({
    skill_id: "example.echo",
    requested_capabilities: ["read_only"],
    manifest_path: "/nonexistent/manifest.json",
  });
}, "MANIFEST_MISSING");

ok("SKILLS_MANIFEST_PRESENT_OK");
ok("SKILLS_CAPABILITY_GATE_BLOCK_OK");
ok("SKILLS_META_ONLY_PROOF_OK");
process.exit(0);

