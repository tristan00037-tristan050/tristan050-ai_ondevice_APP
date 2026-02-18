"use strict";

/**
 * meta-only canonicalizer v2
 * - nested structures preserved (arrays allowed, sorted)
 * - cycles forbidden
 * - finite numbers only
 * - object keys sorted
 * - array elements sorted (if primitive) or stable order (if object)
 * Returns deterministic JSON string.
 */
function canonicalizeMetaRecordV2(x) {
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
      if (seen.has(v)) throw new Error("CANON_CYCLE");
      seen.add(v);

      if (Array.isArray(v)) {
        // Array: preserve nested structure, sort elements if primitive
        const normalized = v.map((item) => norm(item));
        // For primitive arrays, sort for determinism
        // For object arrays, preserve order (nested structure preserved)
        if (normalized.length > 0 && typeof normalized[0] !== "object") {
          normalized.sort((a, b) => {
            if (typeof a === "string" && typeof b === "string") return a.localeCompare(b);
            if (typeof a === "number" && typeof b === "number") return a - b;
            if (typeof a === "boolean" && typeof b === "boolean") return a === b ? 0 : (a ? 1 : -1);
            return String(a).localeCompare(String(b));
          });
        }
        return normalized;
      }

      // Object: sort keys, preserve nested structure
      const out = {};
      const keys = Object.keys(v).sort();
      for (const k of keys) out[k] = norm(v[k]);
      return out;
    }

    throw new Error("CANON_INVALID_TYPE");
  }

  if (typeof x !== "object" || x === null) throw new Error("CANON_ROOT");
  return JSON.stringify(norm(x));
}

module.exports = { canonicalizeMetaRecordV2 };

