'use strict';
const path = require('path');
const { EXIT } = require(path.join(__dirname, 'exit_codes_v1.cjs'));

function getArgOffset() {
  const mode = process.env.VERIFIER_EXEC_MODE;
  if (mode === 'eval') return 1;
  if (mode === 'script') return 2;
  const ea = process.execArgv || [];
  const isEval = ea.some(a =>
    a === '-e' || a === '--eval' || a === '-p' || a === '--print'
  );
  return isEval ? 1 : 2;
}

function getUserArg(idx1Based) {
  const i = Number(idx1Based);
  if (!Number.isInteger(i) || i < 1) {
    process.stdout.write('ERROR_CODE=VERIFY_ARGS_INVALID_INDEX\n');
    process.stdout.write('INVALID_IDX=' + String(idx1Based) + '\n');
    process.exit(EXIT.ARGS_INVALID);
  }
  // eval  모드: offset=1, getUserArg(1)→argv[1], getUserArg(2)→argv[2]
  // script모드: offset=2, getUserArg(1)→argv[2], getUserArg(2)→argv[3]
  const offset = getArgOffset();
  const v = process.argv[offset + (i - 1)];
  if (typeof v !== 'string' || v.trim().length === 0) {
    process.stdout.write('ERROR_CODE=VERIFY_ARGS_MISSING\n');
    process.stdout.write('POSITION=' + i + '\n');
    process.stdout.write('OFFSET_MODE=' + (process.env.VERIFIER_EXEC_MODE || 'auto') + '\n');
    process.exit(EXIT.ARGS_INVALID);
  }
  return v;
}

function expectUserArgsAtLeast(count) {
  const offset = getArgOffset();
  const actual = process.argv.length - offset;
  if (actual < count) {
    process.stdout.write('ERROR_CODE=VERIFY_ARGS_COUNT_TOO_SMALL\n');
    process.stdout.write('REQUIRED=' + count + '\n');
    process.stdout.write('ACTUAL=' + actual + '\n');
    process.exit(EXIT.ARGS_INVALID);
  }
}

module.exports = { getUserArg, expectUserArgsAtLeast, getArgOffset };
