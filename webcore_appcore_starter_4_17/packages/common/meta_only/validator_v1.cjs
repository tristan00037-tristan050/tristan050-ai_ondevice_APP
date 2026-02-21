"use strict";

/**
 * validator_v1.cjs
 * 목적: 런타임(require)에서 항상 존재하는 단일 소스 meta-only validator를 제공한다.
 * 금지: 원문/프롬프트/본문 키(prompt/raw/text/messages/content 등) 유입
 */

const FORBIDDEN_KEYS = new Set([
  "prompt", "raw", "text", "messages", "content",
  "document", "documents", "source", "sources",
]);

function assertMetaOnly(obj) {
  if (obj == null || typeof obj !== "object") {
    throw new Error("META_ONLY: input must be object");
  }

  const stack = [obj];
  while (stack.length) {
    const cur = stack.pop();
    for (const k of Object.keys(cur)) {
      if (FORBIDDEN_KEYS.has(k)) {
        throw new Error(`META_ONLY: forbidden key '${k}'`);
      }
      const v = cur[k];
      if (v && typeof v === "object") stack.push(v);
    }
  }
  return true;
}

function validateMetaOnlyOrThrow(obj, context = "") {
  try {
    assertMetaOnly(obj);
  } catch (e) {
    const prefix = context ? `${context}: ` : "";
    const msg = e && e.message ? e.message : String(e);
    throw new Error(prefix + msg);
  }
}

module.exports = {
  assertMetaOnly,
  validateMetaOnlyOrThrow,
};
