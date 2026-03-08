'use strict';

function isEnforced(v) {
  return String(v ?? '0') === '1';
}

module.exports = { isEnforced };
