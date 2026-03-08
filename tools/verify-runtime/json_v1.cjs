'use strict';
const fs = require('fs');

function parseJsonFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('VERIFY_JSON_NOT_OBJECT');
  }
  return parsed;
}

module.exports = { parseJsonFile };
