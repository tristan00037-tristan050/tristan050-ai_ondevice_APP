'use strict';

function getUserArg(idx1Based) {
  const i = Number(idx1Based);
  if (!Number.isInteger(i) || i < 1) {
    throw new Error('VERIFY_ARGS_INVALID_INDEX');
  }
  const v = process.argv[i];
  if (typeof v !== 'string' || v.length === 0) {
    throw new Error(`VERIFY_ARGS_MISSING_${i}`);
  }
  return v;
}

function expectUserArgsAtLeast(count) {
  const n = Number(count);
  if (!Number.isInteger(n) || n < 1) {
    throw new Error('VERIFY_ARGS_INVALID_COUNT');
  }
  if ((process.argv.length - 1) < n) {
    throw new Error('VERIFY_ARGS_COUNT_TOO_SMALL');
  }
}

module.exports = { getUserArg, expectUserArgsAtLeast };
