"use strict";

/**
 * meta-only canonicalizer v1
 * - arrays forbidden
 * - cycles forbidden
 * - finite numbers only
 * - object keys sorted
 * Returns deterministic JSON string.
 */
function canonicalizeMetaRecordV1(x) {
  const seen = new Set();

  function norm(v) {
    if (v === null) return null;
    const t = typeof v;

    if (t === "boolean" || t === "string") return v;

    if (t === "number") {
      if (!Number.isFinite(v)) throw new Error("CANON_NON_FINITE_NUMBER");
      return v;
    }

    if (t === "object") {
      if (Array.isArray(v)) throw new Error("CANON_ARRAY_FORBIDDEN");
      if (seen.has(v)) throw new Error("CANON_CYCLE");
      seen.add(v);

      const out = {};
      const keys = Object.keys(v).sort();
      for (const k of keys) out[k] = norm(v[k]);
      return out;
    }

    throw new Error("CANON_INVALID_TYPE");
  }

  if (typeof x !== "object" || x === null || Array.isArray(x)) throw new Error("CANON_ROOT");
  return JSON.stringify(norm(x));
}

module.exports = { canonicalizeMetaRecordV1 };
