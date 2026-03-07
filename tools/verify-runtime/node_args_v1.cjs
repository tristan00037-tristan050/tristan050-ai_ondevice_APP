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
  if ((process.argv.length - 1) < count) {
    throw new Error('VERIFY_ARGS_COUNT_TOO_SMALL');
  }
}

module.exports = { getUserArg, expectUserArgsAtLeast };
