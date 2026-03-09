'use strict';
const fs = require('fs');
const path = require('path');
const { EXIT } = require(path.join(__dirname, 'exit_codes_v1.cjs'));

const RUN_GUARD_RE =
  /^\s*run_guard\s+"([^"]+)"\s+bash\s+(scripts\/verify\/[A-Za-z0-9._/-]+\.sh)\s*(?:#.*)?$/;

function parseRunGuardLines(anchorPath) {
  const lines = fs.readFileSync(anchorPath, 'utf8').split('\n');
  const out = [];
  let inHeredoc = false;
  let heredocEnd = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!inHeredoc) {
      const hd = line.match(/(?:^|[;\s])<<-?\s*['"]?([A-Za-z0-9_]+)['"]?\s*$/);
      if (hd) { inHeredoc = true; heredocEnd = hd[1]; continue; }
    } else {
      if (line.replace(/^\t+/, '').trim() === heredocEnd) {
        inHeredoc = false; heredocEnd = null;
      }
      continue;
    }
    if (/^\s*#/.test(line)) continue;
    const m = line.match(RUN_GUARD_RE);
    if (!m) continue;
    out.push({ guard_name: m[1], script_path: m[2], line_number: i + 1 });
  }
  return out;
}

function assertUniqueOrderedPaths(actualRows, expectedPaths) {
  const actual = actualRows.map(function(x) { return x.script_path; });
  const seen = new Set();
  for (var j = 0; j < actual.length; j++) {
    var p = actual[j];
    if (seen.has(p)) {
      process.stdout.write('ERROR_CODE=VERIFIER_CHAIN_DUPLICATE\n');
      process.stdout.write('DUPLICATE=' + p + '\n');
      process.exit(EXIT.CHAIN_ORDER_INVALID);
    }
    seen.add(p);
  }
  for (var i = 0; i < expectedPaths.length; i++) {
    if (actual[i] !== expectedPaths[i]) {
      process.stdout.write('ERROR_CODE=VERIFIER_CHAIN_ORDER_MISMATCH\n');
      process.stdout.write('EXPECTED=' + expectedPaths[i] + '\n');
      process.stdout.write('ACTUAL=' + (actual[i] || 'MISSING') + '\n');
      process.stdout.write('AT_INDEX=' + i + '\n');
      process.exit(EXIT.CHAIN_ORDER_INVALID);
    }
  }
}

module.exports = { parseRunGuardLines, assertUniqueOrderedPaths };
