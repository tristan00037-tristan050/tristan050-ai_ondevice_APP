/**
 * P2-AI-01: Stable Fingerprint
 * 목적: per-request 값 제외, pack param(salt) + 3블록 내용만 사용
 */

import crypto from "node:crypto";

function stableStringify(obj: any): string {
  if (obj === null || typeof obj !== "object") return JSON.stringify(obj);
  if (Array.isArray(obj)) return `[${obj.map(stableStringify).join(",")}]`;
  const keys = Object.keys(obj).sort();
  return `{${keys.map(k => JSON.stringify(k)+":"+stableStringify(obj[k])).join(",")}}`;
}

export function fingerprintSha256(input: {
  pack_salt: number;
  rules: any;
  steps: any;
  checks: any;
}): string {
  const payload = stableStringify({
    pack_salt: input.pack_salt,
    rules: input.rules,
    steps: input.steps,
    checks: input.checks,
  });
  return crypto.createHash("sha256").update(payload).digest("hex");
}

