/**
 * RFC 8785 JSON Canonicalization Scheme (JCS) – minimal compliant canonicalizer.
 * - Deterministic object key ordering (UTF-16 code unit order, JS default).
 * - JSON primitives serialized via JSON.stringify on normalized structure.
 * - Reject NaN/Infinity at runtime via number check.
 *
 * Note: Full RFC details include precise number formatting per ECMAScript.
 * This implementation enforces: finite numbers only, stable key ordering, stable string escaping via JSON.stringify.
 */
export function jcsCanonicalize(value: unknown): string {
  const norm = normalize(value);
  return JSON.stringify(norm);
}

function normalize(v: unknown): any {
  if (v === null) return null;
  const t = typeof v;

  if (t === 'string' || t === 'boolean') return v;

  if (t === 'number') {
    if (!Number.isFinite(v as number)) throw new Error('JCS: NaN/Infinity forbidden');
    // JSON.stringify uses ECMAScript number serialization; RFC 8785 builds on this.
    return v;
  }

  if (Array.isArray(v)) return v.map(normalize);

  if (t === 'object') {
    const obj = v as Record<string, unknown>;
    const keys = Object.keys(obj).sort(); // deterministic property ordering
    const out: Record<string, any> = {};
    for (const k of keys) out[k] = normalize(obj[k]);
    return out;
  }

  // undefined / function / symbol are not valid JSON
  throw new Error(`JCS: unsupported type ${t}`);
}

