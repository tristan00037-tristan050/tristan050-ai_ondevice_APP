/**
 * Minimal JCS-like canonicalization (stable JSON stringify).
 * Note: This is a deterministic stringify to remove key-order ambiguity.
 * Hardening 목표: server/tests/sdk가 동일 구현을 공유하는 것.
 */
export function canonicalizeJson(input: unknown): string {
  return JSON.stringify(sortRec(input));
}

function sortRec(x: any): any {
  if (x === null || x === undefined) return x;
  if (Array.isArray(x)) return x.map(sortRec);
  if (typeof x === "object") {
    const keys = Object.keys(x).sort();
    const out: Record<string, any> = {};
    for (const k of keys) out[k] = sortRec(x[k]);
    return out;
  }
  return x;
}

