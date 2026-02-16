#!/usr/bin/env node
/* eslint-disable no-console */
"use strict";

const fs = require("fs");
const path = require("path");

function err(msg, code) {
  const e = new Error(String(msg));
  e.code = code || "BLOCK";
  return e;
}

function loadManifest(manifestPath) {
  if (!manifestPath || typeof manifestPath !== "string") {
    throw err("BLOCK: manifest_path required", "MANIFEST_PATH");
  }

  const absPath = path.isAbsolute(manifestPath)
    ? manifestPath
    : path.resolve(process.cwd(), manifestPath);

  if (!fs.existsSync(absPath)) {
    throw err(`BLOCK: manifest not found: ${absPath}`, "MANIFEST_MISSING");
  }

  let manifest;
  try {
    const content = fs.readFileSync(absPath, "utf-8");
    manifest = JSON.parse(content);
  } catch (e) {
    throw err(`BLOCK: manifest parse failed: ${e.message}`, "MANIFEST_PARSE");
  }

  if (!manifest || typeof manifest !== "object") {
    throw err("BLOCK: manifest must be an object", "MANIFEST_FORMAT");
  }

  if (!Array.isArray(manifest.skills)) {
    throw err("BLOCK: manifest.skills must be an array", "MANIFEST_FORMAT");
  }

  return manifest;
}

function findSkill(manifest, skillId) {
  if (!skillId || typeof skillId !== "string") {
    throw err("BLOCK: skill_id required", "SKILL_ID");
  }

  const skill = manifest.skills.find((s) => s.skill_id === skillId);
  if (!skill) {
    throw err(`BLOCK: skill_id not registered: ${skillId}`, "SKILL_NOT_REGISTERED");
  }

  return skill;
}

function validateCapabilities(skill, requestedCapabilities) {
  if (!Array.isArray(requestedCapabilities)) {
    throw err("BLOCK: requested_capabilities must be an array", "CAPABILITIES_FORMAT");
  }

  const manifestCapabilities = skill.capabilities || [];
  const manifestSet = new Set(manifestCapabilities);

  for (const cap of requestedCapabilities) {
    if (!manifestSet.has(cap)) {
      throw err(
        `BLOCK: capability not allowed: ${cap} (manifest: ${manifestCapabilities.join(", ")})`,
        "CAPABILITY_NOT_ALLOWED"
      );
    }
  }

  return true;
}

function createMetaOnlyProof(skill, skillId, requestedCapabilities) {
  return {
    skill_id: skillId,
    capabilities: requestedCapabilities,
    meta_only_proof: skill.meta_only_proof === true,
    timestamp_utc: new Date().toISOString(),
  };
}

function gateSkillsRuntimeV1(input) {
  const { skill_id, requested_capabilities = [], manifest_path } = input || {};

  // 1) Load manifest
  const manifest = loadManifest(manifest_path);

  // 2) Find skill
  const skill = findSkill(manifest, skill_id);

  // 3) Validate capabilities
  validateCapabilities(skill, requested_capabilities);

  // 3-A) Fail-closed: meta-only proof must be true
  if (skill.meta_only_proof !== true) {
    const e = new Error("BLOCK: meta-only proof required");
    e.code = "SKILL_META_ONLY_REQUIRED";
    throw e;
  }

  // 4) Generate meta-only proof
  const proof = createMetaOnlyProof(skill, skill_id, requested_capabilities);

  return {
    allow: true,
    proof,
  };
}

module.exports = {
  gateSkillsRuntimeV1,
  loadManifest,
  findSkill,
  validateCapabilities,
  createMetaOnlyProof,
};

