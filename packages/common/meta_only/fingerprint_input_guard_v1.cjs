"use strict";

/**
 * Fingerprint input guard v1
 * - meta-only
 * - fail-closed
 * - code-only reason
 */
const BANNED = new Set(["request_id","ts_utc","nonce","manifest","run_id"]);

function assertNoPerRequestKeysV1(x) {
  if (typeof x !== "object" || x === null || Array.isArray(x)) {
    const e = new Error("FP_INPUT_ROOT_INVALID_V1");
    e.code = "FP_INPUT_ROOT_INVALID_V1";
    throw e;
  }
  for (const k of Object.keys(x)) {
    if (BANNED.has(k)) {
      const e = new Error("FP_INPUT_BANNED_KEY_V1");
      e.code = "FP_INPUT_BANNED_KEY_V1";
      e.meta = { banned_key: k };
      throw e;
    }
  }
  return true;
}

module.exports = { assertNoPerRequestKeysV1, BANNED_KEYS_V1: Array.from(BANNED) };
