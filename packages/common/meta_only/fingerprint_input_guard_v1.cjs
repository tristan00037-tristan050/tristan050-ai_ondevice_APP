"use strict";

/**
 * Fingerprint input guard v1 (nested)
 * - meta-only
 * - fail-closed
 * - code-only reason
 * - scans nested objects/arrays for banned keys
 * - cycle-safe + max depth/node limits to avoid DoS / flakiness
 */
const BANNED = new Set(["request_id", "ts_utc", "nonce", "manifest", "run_id"]);

const DEFAULT_LIMITS = {
  maxDepth: 32,
  maxNodes: 20000,
};

function makeErr(code, meta) {
  const e = new Error(code);
  e.code = code;
  if (meta) e.meta = meta; // meta-only: path/key only, no values
  return e;
}

function assertNoPerRequestKeysV1(x, limits = DEFAULT_LIMITS) {
  const { maxDepth, maxNodes } = limits || DEFAULT_LIMITS;

  let nodes = 0;
  const seen = new Set();

  function visit(v, depth, path) {
    nodes += 1;
    if (nodes > maxNodes) throw makeErr("FP_INPUT_TOO_LARGE_V1", { path });

    if (depth > maxDepth) throw makeErr("FP_INPUT_TOO_DEEP_V1", { path });

    if (v === null) return;
    const t = typeof v;

    if (t === "string" || t === "number" || t === "boolean") return;

    if (t !== "object") throw makeErr("FP_INPUT_INVALID_TYPE_V1", { path });

    if (seen.has(v)) throw makeErr("FP_INPUT_CYCLE_V1", { path });
    seen.add(v);

    if (Array.isArray(v)) {
      for (let i = 0; i < v.length; i++) {
        visit(v[i], depth + 1, `${path}[${i}]`);
      }
      return;
    }

    // object
    for (const k of Object.keys(v)) {
      if (BANNED.has(k)) throw makeErr("FP_INPUT_BANNED_KEY_V1", { path: `${path}.${k}` });
      visit(v[k], depth + 1, `${path}.${k}`);
    }
  }

  if (typeof x !== "object" || x === null) throw makeErr("FP_INPUT_ROOT_INVALID_V1", { path: "$" });

  visit(x, 0, "$");
  return true;
}

module.exports = { assertNoPerRequestKeysV1, BANNED_KEYS_V1: Array.from(BANNED) };
