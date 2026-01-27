export type MetaOnlySSOT = {
  schema_name: string;
  allowed_keys: string[];
  forbidden_patterns: string[];
  max_string_len: number;
};

function isAllowedKey(key: string, allowed: string[]) {
  for (const a of allowed) {
    if (a.endsWith("*")) {
      const prefix = a.slice(0, -1);
      if (key.startsWith(prefix)) return true;
    } else {
      if (key === a) return true;
    }
  }
  return false;
}

function hasForbiddenPattern(s: string, patterns: string[]) {
  const low = s.toLowerCase();
  return patterns.some((p) => low.includes(p.toLowerCase()));
}

// meta-only: only numbers/booleans/null and short strings within limit
export function validateMetaOnlyWithSSOT(
  payload: any,
  ssot: MetaOnlySSOT
): { ok: true } | { ok: false; reason_code: string; detail: any } {
  if (payload === null || payload === undefined) return { ok: true };
  if (typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, reason_code: "META_ONLY_NOT_OBJECT", detail: { type: typeof payload } };
  }

  for (const [k, v] of Object.entries(payload)) {
    if (!isAllowedKey(k, ssot.allowed_keys)) {
      return { ok: false, reason_code: "META_ONLY_KEY_NOT_ALLOWED", detail: { key: k, schema: ssot.schema_name } };
    }

    if (v === null) continue;

    const t = typeof v;
    if (t === "number" || t === "boolean") continue;

    if (t === "string") {
      const s = String(v);
      if (s.length > ssot.max_string_len) {
        return { ok: false, reason_code: "META_ONLY_STRING_TOO_LONG", detail: { key: k, len: s.length, max: ssot.max_string_len } };
      }
      if (hasForbiddenPattern(s, ssot.forbidden_patterns)) {
        return { ok: false, reason_code: "META_ONLY_FORBIDDEN_PATTERN", detail: { key: k } };
      }
      continue;
    }

    // arrays/objects/functions/etc not allowed
    return { ok: false, reason_code: "META_ONLY_VALUE_TYPE_NOT_ALLOWED", detail: { key: k, type: t } };
  }

  return { ok: true };
}
