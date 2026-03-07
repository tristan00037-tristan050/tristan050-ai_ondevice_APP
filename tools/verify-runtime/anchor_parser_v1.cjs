'use strict';
const fs = require('fs');

function parseRunGuardLines(file) {
  const src = fs.readFileSync(file, 'utf8').split('\n');
  const re = /^\s*run_guard\s+"[^"]+"\s+bash\s+(scripts\/verify\/[A-Za-z0-9._/-]+)\s*$/;
  const out = [];
  for (const line of src) {
    const m = line.match(re);
    if (m) out.push(m[1]);
  }
  return out;
}

module.exports = { parseRunGuardLines };
