#!/usr/bin/env bash
set -euo pipefail

DOCKERLESS_REPORT_RUN_OK=0
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0
DOCKERLESS_REPORT_SKIPPED=0

finish() {
  echo "DOCKERLESS_REPORT_RUN_OK=${DOCKERLESS_REPORT_RUN_OK}"
  echo "DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=${DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK}"
  echo "DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=${DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK}"
  echo "DOCKERLESS_REPORT_SKIPPED=${DOCKERLESS_REPORT_SKIPPED}"
}
trap finish EXIT

# ENFORCE=1인 경우에만 fail-closed로 강제한다. 그 외 워크플로는 무조건 SKIP(리포트 유무와 무관).
ENFORCE="${DOCKERLESS_REPORT_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  DOCKERLESS_REPORT_SKIPPED=1
  exit 0
fi

OUT_ROOT="${OUT_ROOT:-out}"
REPORT_ROOT="${REPO_GUARD_REPORTS_ROOT:-${OUT_ROOT}/ops/reports}"
report="${REPORT_ROOT}/repo_contracts_latest.json"
if [ ! -f "$report" ]; then
  report="docs/ops/reports/repo_contracts_latest.json"
fi

# ENFORCE=1인데 리포트가 없으면 FAIL
test -f "$report" || { echo "ERROR_CODE=REPORT_MISSING"; exit 1; }

node - "$report" <<'NODE'
const fs = require("fs");
const a1 = process.argv[1];
const a2 = process.argv[2];
const reportPath = (!a1 || a1 === "-") ? a2 : a1;
if (!reportPath) process.exit(20);

const j = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const keys = (j && j.keys) || {};

function is01(v){ return v === "0" || v === "1"; }
function must01(k){
  if(!(k in keys)) process.exit(21);
  if(!is01(keys[k])) process.exit(22);
}
must01("DOCKER_IT_NET_DB_SVCNAME_V1_OK");
must01("HOST_DOCKER_INTERNAL_FORBIDDEN_OK");
process.exit(0);
NODE

DOCKERLESS_REPORT_RUN_OK=1
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=1
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=1
exit 0
