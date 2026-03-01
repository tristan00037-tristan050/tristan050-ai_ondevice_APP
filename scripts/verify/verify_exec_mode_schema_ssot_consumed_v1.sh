#!/usr/bin/env bash
set -euo pipefail

EXEC_MODE_SCHEMA_SSOT_CONSUMED_OK=0
finish(){ echo "EXEC_MODE_SCHEMA_SSOT_CONSUMED_OK=${EXEC_MODE_SCHEMA_SSOT_CONSUMED_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/EXEC_MODE_SCHEMA_V1.json"
test -f "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }

# 토큰 대신 schema_id 존재로 최소 검증(SSOT는 JSON)
if ! node -e '
const fs = require("fs");
const j = JSON.parse(fs.readFileSync("docs/ops/contracts/EXEC_MODE_SCHEMA_V1.json","utf8"));
if (!j.schema_id || !Array.isArray(j.required_keys) || j.required_keys.length === 0) process.exit(1);
' 2>/dev/null; then
  echo "ERROR_CODE=SSOT_INVALID"
  exit 1
fi

# 하드코딩 required key 목록(대표 패턴) 남아 있으면 BLOCK — exec_mode 영역만 검사
if grep -RIn 'required_keys=\(|REQUIRED_KEYS=' tools/exec_mode scripts/verify/verify_exec_mode*.sh 2>/dev/null | grep -v 'EXEC_MODE_SCHEMA_V1.json' >/dev/null 2>&1; then
  echo "ERROR_CODE=HARDCODED_REQUIRED_KEYS_FOUND"
  exit 1
fi

EXEC_MODE_SCHEMA_SSOT_CONSUMED_OK=1
exit 0
