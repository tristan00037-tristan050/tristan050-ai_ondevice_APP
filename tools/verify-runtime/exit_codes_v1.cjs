'use strict';

const EXIT = Object.freeze({
  JSON_INVALID: 10,
  SCHEMA_MISSING: 11,
  DIGEST_MISMATCH: 12,
  LINK_MISSING: 13,
  META_ONLY_VIOLATION: 14,
  UNEXPECTED_RC: 90,
});

module.exports = { EXIT };
