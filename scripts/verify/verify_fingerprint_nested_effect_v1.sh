#!/usr/bin/env bash
set -euo pipefail

# P5-AI-P0-02: Fingerprint Nested Effect V1
# - 판정만 (verify=판정만, build/install/download/network 금지)
# - nested 구조 보존 selftest

AI_INPUT_CANON_PRESERVE_NESTED_V1_OK=0

trap 'echo "AI_INPUT_CANON_PRESERVE_NESTED_V1_OK=${AI_INPUT_CANON_PRESERVE_NESTED_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="packages/common/meta_only/canonicalize_v2.cjs"

# 1) SSOT 존재 확인
[ -f "$SSOT" ] || { echo "BLOCK: missing SSOT: $SSOT"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# 2) nested 구조 보존 selftest
# Test 1: nested object structure preserved
TEST1_INPUT='{"a":1,"b":{"c":2,"d":3}}'
TEST1_OUTPUT="$(node -e "const {canonicalizeMetaRecordV2} = require('./$SSOT'); console.log(canonicalizeMetaRecordV2($TEST1_INPUT))")"
TEST1_EXPECTED='{"a":1,"b":{"c":2,"d":3}}'
if [ "$TEST1_OUTPUT" != "$TEST1_EXPECTED" ]; then
  echo "BLOCK: nested object structure not preserved"
  echo "Expected: $TEST1_EXPECTED"
  echo "Got: $TEST1_OUTPUT"
  exit 1
fi

# Test 2: nested array structure preserved
TEST2_INPUT='{"items":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}'
TEST2_OUTPUT="$(node -e "const {canonicalizeMetaRecordV2} = require('./$SSOT'); console.log(canonicalizeMetaRecordV2($TEST2_INPUT))")"
# Array order should be preserved for object arrays
if ! echo "$TEST2_OUTPUT" | grep -q '"items"'; then
  echo "BLOCK: nested array structure not preserved"
  exit 1
fi

# Test 3: primitive array sorted for determinism
TEST3_INPUT='{"nums":[3,1,2]}'
TEST3_OUTPUT="$(node -e "const {canonicalizeMetaRecordV2} = require('./$SSOT'); console.log(canonicalizeMetaRecordV2($TEST3_INPUT))")"
TEST3_EXPECTED='{"nums":[1,2,3]}'
if [ "$TEST3_OUTPUT" != "$TEST3_EXPECTED" ]; then
  echo "BLOCK: primitive array not sorted for determinism"
  echo "Expected: $TEST3_EXPECTED"
  echo "Got: $TEST3_OUTPUT"
  exit 1
fi

AI_INPUT_CANON_PRESERVE_NESTED_V1_OK=1
exit 0

