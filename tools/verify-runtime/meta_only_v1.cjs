'use strict';

const FORBIDDEN_KEYS = new Set([
  'raw', 'origin', 'content', 'body', 'full_output', 'stdout', 'stderr'
]);

function checkMetaOnly(obj, depth = 0, maxDepth = 5, maxStringLen = 500) {
  if (depth > maxDepth) throw new Error('VERIFY_META_ONLY_DEPTH_EXCEEDED');
  if (!obj || typeof obj !== 'object') return;

  for (const [k, v] of Object.entries(obj)) {
    if (FORBIDDEN_KEYS.has(k)) throw new Error('VERIFY_META_ONLY_FORBIDDEN_KEY');
    if (typeof v === 'string' && v.length > maxStringLen) {
      throw new Error('VERIFY_META_ONLY_STRING_TOO_LONG');
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      checkMetaOnly(v, depth + 1, maxDepth, maxStringLen);
    }
    if (Array.isArray(v)) {
      for (const item of v) {
        if (item && typeof item === 'object') {
          checkMetaOnly(item, depth + 1, maxDepth, maxStringLen);
        }
      }
    }
  }
}

module.exports = { checkMetaOnly };
