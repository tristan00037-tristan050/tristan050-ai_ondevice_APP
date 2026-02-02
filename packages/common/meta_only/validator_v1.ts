export const BANNED_KEYS = new Set([
  "raw_text","prompt","messages","document_body","input_text","output_text",
  "database_url","private_key","signing_key","seed"
]);

export type MetaJson = null | boolean | number | string | MetaJsonObj;
export type MetaJsonObj = { [k: string]: MetaJson };

export function assertMetaOnly(
  x: unknown,
  opts = { maxDepth: 4, maxString: 512, maxKeys: 64 }
): asserts x is MetaJsonObj {
  const seen = new Set<unknown>();

  function walk(v: any, depth: number) {
    if (depth > opts.maxDepth) throw new Error("META_ONLY_DEPTH");
    if (v === null) return;

    const t = typeof v;
    if (t === "string") {
      if (v.length > opts.maxString) throw new Error("META_ONLY_STRING_TOO_LONG");
      return;
    }
    if (t === "number" || t === "boolean") return;

    if (Array.isArray(v)) throw new Error("META_ONLY_ARRAY_FORBIDDEN");
    if (t !== "object") throw new Error("META_ONLY_INVALID_TYPE");

    if (seen.has(v)) throw new Error("META_ONLY_CYCLE");
    seen.add(v);

    const keys = Object.keys(v);
    if (keys.length > opts.maxKeys) throw new Error("META_ONLY_TOO_MANY_KEYS");

    for (const k of keys) {
      if (BANNED_KEYS.has(k)) throw new Error("META_ONLY_BANNED_KEY");
      walk((v as any)[k], depth + 1);
    }
  }

  if (typeof x !== "object" || x === null || Array.isArray(x)) throw new Error("META_ONLY_ROOT");
  walk(x, 0);
}

