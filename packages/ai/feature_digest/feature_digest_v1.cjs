'use strict';

const fs = require('fs');
const path = require('path');

// SSOT allowlist (__dirname so path is independent of process.cwd())
const ALLOWLIST_PATH = path.join(__dirname, '..', '..', '..', 'docs', 'ops', 'contracts', 'FEATURE_DIGEST_ALLOWED_KEYS_V1.txt');

function loadAllowlist() {
  const txt = fs.readFileSync(ALLOWLIST_PATH, 'utf8');
  return new Set(
    txt.split('\n')
      .map(s => s.trim())
      .filter(Boolean)
  );
}

function assertPrimitive(v) {
  if (v === null) return;
  const t = typeof v;
  if (t === 'string') {
    if (v.length > 64) throw new Error('FEATURE_DIGEST_STRING_TOO_LONG');
    return;
  }
  if (t === 'number') {
    if (!Number.isFinite(v)) throw new Error('FEATURE_DIGEST_NONFINITE_NUMBER');
    // -0 normalize
    if (Object.is(v, -0)) throw new Error('FEATURE_DIGEST_NEGATIVE_ZERO');
    return;
  }
  if (t === 'boolean') return;
  throw new Error('FEATURE_DIGEST_NON_PRIMITIVE');
}

/**
 * inputMeta: meta-only object (arrays/objects nested are not accepted here)
 * returns: feature_digest_v1 object with allowed keys only
 */
function featureDigestV1(inputMeta) {
  if (inputMeta === null || typeof inputMeta !== 'object' || Array.isArray(inputMeta)) {
    throw new Error('FEATURE_DIGEST_INPUT_NOT_OBJECT');
  }

  const allow = loadAllowlist();
  const out = {};

  for (const k of Object.keys(inputMeta)) {
    if (!allow.has(k)) throw new Error('FEATURE_DIGEST_KEY_NOT_ALLOWED:' + k);
    const v = inputMeta[k];
    assertPrimitive(v);
    out[k] = v;
  }

  // Fail-closed: must contain at least model_pack_id + pack_version_id to be meaningful
  if (!Object.prototype.hasOwnProperty.call(out, 'model_pack_id')) {
    throw new Error('FEATURE_DIGEST_MISSING_model_pack_id');
  }
  if (!Object.prototype.hasOwnProperty.call(out, 'pack_version_id')) {
    throw new Error('FEATURE_DIGEST_MISSING_pack_version_id');
  }

  return out;
}

module.exports = { featureDigestV1, ALLOWLIST_PATH };
