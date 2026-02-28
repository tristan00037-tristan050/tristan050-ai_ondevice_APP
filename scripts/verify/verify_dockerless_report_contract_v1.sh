#!/usr/bin/env bash
set -euo pipefail

DOCKERLESS_REPORT_RUN_OK=0
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0

finish() {
  echo "DOCKERLESS_REPORT_RUN_OK=${DOCKERLESS_REPORT_RUN_OK}"
  echo "DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=${DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK}"
  echo "DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=${DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK}"
}
trap finish EXIT

OUT_ROOT="${OUT_ROOT:-out}"
report="${OUT_ROOT}/ops/reports/repo_contracts_latest.json"

test -f "$report" || { echo "ERROR_CODE=REPORT_MISSING"; exit 1; }

node - "$report" <<'NODE'
const fs = require("fs");
const p = process.argv[2];
const j = JSON.parse(fs.readFileSync(p, "utf8"));
const keys = (j && j.keys) || {};

function is01(v){ return v === "0" || v === "1"; }
function must01(k){
  if(!(k in keys)) process.exit(21);
  if(!is01(keys[k])) process.exit(22);
}

must01("DOCKER_IT_NET_DB_SVCNAME_V1_OK");
must01("HOST_DOCKER_INTERNAL_FORBIDDEN_OK");

// dockerless 환경에서는 DB 네트워크 관련 키가 degrade(0)일 수 있음.
// 핵심은 "결측 금지(0/1 반드시 emit)"와 "정적 정책 키 always-on(결측 금지)".
process.exit(0);
NODE

DOCKERLESS_REPORT_RUN_OK=1
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=1
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=1
exit 0
